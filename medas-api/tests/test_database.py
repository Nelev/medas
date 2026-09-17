"""Tests for engine lifecycle and the session dependency.

No real engine is built anywhere here: create_async_engine is patched out.
These tests are about the module's own bookkeeping -- the globals, the
idempotency guard and the rollback path -- not about SQLAlchemy.
"""

import pytest
from pydantic import SecretStr

from database import database as db
from database.settings import DbSettings


@pytest.fixture(autouse=True)
def _reset_engine_globals():
    """Clear the module globals around every test.

    _engine and _session_factory outlive a test, so without this the first
    test to call init_engine() decides what every later test sees.
    """
    db._engine = None
    db._session_factory = None
    yield
    db._engine = None
    db._session_factory = None


@pytest.fixture
def settings(monkeypatch) -> DbSettings:
    """Settings that do not depend on the developer's .env."""
    fixed = DbSettings(
        _env_file=None,
        database_password=SecretStr("s3cret"),
        database_host="db.internal",
        db_pool_size=7,
        db_max_overflow=3,
        db_pool_timeout=11,
        db_echo=True,
    )
    monkeypatch.setattr(db, "get_settings", lambda: fixed)
    return fixed


class FakeEngine:
    def __init__(self) -> None:
        self.disposed = 0

    async def dispose(self) -> None:
        self.disposed += 1


class FakeSession:
    """Async context manager standing in for AsyncSession."""

    def __init__(self) -> None:
        self.rolled_back = False
        self.exited = False

    async def rollback(self) -> None:
        self.rolled_back = True

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *exc_info) -> bool:
        self.exited = True
        return False


@pytest.fixture
def engine_spy(monkeypatch):
    """Capture create_async_engine calls instead of opening a pool."""
    calls = []

    def _fake_create(url, **kwargs):
        calls.append((url, kwargs))
        return FakeEngine()

    monkeypatch.setattr(db, "create_async_engine", _fake_create)
    return calls


# --- init_engine ------------------------------------------------------------


def test_init_engine_builds_an_engine_and_a_session_factory(settings, engine_spy):
    engine = db.init_engine()

    assert engine is db._engine
    assert db._session_factory is not None
    assert len(engine_spy) == 1


def test_init_engine_is_idempotent(settings, engine_spy):
    # The lifespan calls it once, but a second call must not replace a live
    # pool -- sessions already handed out would be bound to the old engine.
    first = db.init_engine()
    second = db.init_engine()

    assert first is second
    assert len(engine_spy) == 1


def test_init_engine_passes_pool_settings_through(settings, engine_spy):
    db.init_engine()
    url, kwargs = engine_spy[0]

    # database_url is a property returning a fresh URL each access, so this
    # is equality, not identity.
    assert url == settings.database_url
    assert kwargs["pool_size"] == 7
    assert kwargs["max_overflow"] == 3
    assert kwargs["pool_timeout"] == 11
    assert kwargs["echo"] is True


def test_init_engine_enables_pre_ping(settings, engine_spy):
    # Postgres drops idle connections; without pre-ping the first request
    # after an idle period fails instead of transparently reconnecting.
    db.init_engine()
    _, kwargs = engine_spy[0]

    assert kwargs["pool_pre_ping"] is True


# --- dispose_engine ---------------------------------------------------------


async def test_dispose_engine_closes_the_pool_and_clears_state(settings, engine_spy):
    engine = db.init_engine()

    await db.dispose_engine()

    assert engine.disposed == 1
    assert db._engine is None
    assert db._session_factory is None


async def test_dispose_engine_is_safe_when_never_initialised():
    # The lifespan's shutdown half runs even if startup failed part-way.
    await db.dispose_engine()

    assert db._engine is None
    assert db._session_factory is None


async def test_engine_can_be_rebuilt_after_disposal(settings, engine_spy):
    db.init_engine()
    await db.dispose_engine()
    db.init_engine()

    assert len(engine_spy) == 2


# --- get_session ------------------------------------------------------------


async def test_get_session_raises_when_the_engine_is_not_initialised():
    # A clearer failure than whatever None.__call__ would produce.
    agen = db.get_session()

    with pytest.raises(RuntimeError, match="not initialised"):
        await anext(agen)


async def test_get_session_yields_a_session_and_closes_it(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(db, "_session_factory", lambda: session)

    agen = db.get_session()
    yielded = await anext(agen)
    assert yielded is session

    with pytest.raises(StopAsyncIteration):
        await anext(agen)

    assert session.exited
    assert not session.rolled_back


async def test_get_session_rolls_back_when_the_caller_raises(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(db, "_session_factory", lambda: session)

    agen = db.get_session()
    await anext(agen)

    with pytest.raises(ValueError, match="boom"):
        await agen.athrow(ValueError("boom"))

    assert session.rolled_back
    assert session.exited


async def test_get_session_re_raises_rather_than_swallowing(monkeypatch):
    # Rolling back and then returning normally would hand the client a 200
    # for a request whose work was discarded.
    session = FakeSession()
    monkeypatch.setattr(db, "_session_factory", lambda: session)

    agen = db.get_session()
    await anext(agen)

    with pytest.raises(ValueError):
        await agen.athrow(ValueError("boom"))
