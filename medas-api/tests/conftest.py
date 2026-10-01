"""Shared fixtures.

Everything here exists to undo process-wide state that would otherwise leak
between tests.
"""

import pytest

from auth import get_auth_settings
from database.settings import DbSettings, get_settings
from ratelimit import limiter


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """Drop the lru_cache around get_settings and get_auth_settings.

    Without this the first test to call either freezes the result for the
    whole session, so a later test that patches the environment silently
    reads the earlier test's settings.
    """
    get_settings.cache_clear()
    get_auth_settings.cache_clear()
    yield
    get_settings.cache_clear()
    get_auth_settings.cache_clear()


@pytest.fixture(autouse=True)
def _no_database_env(monkeypatch):
    """Remove every DbSettings variable from the process environment.

    load_dotenv() runs at import in several modules and copies .env into
    os.environ, where it wins over a test's _env_file=None. Without this a
    developer's local values (DATABASE_PORT=5433 for the Docker database)
    decide what the defaults tests see, and which modules happened to be
    imported first decides whether they do.
    """
    for name in DbSettings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


@pytest.fixture(autouse=True)
def _no_real_clerk_key(monkeypatch):
    """A placeholder secret key, so AuthSettings loads in every test.

    Set in the environment, which wins over .env: a developer's real key is
    never what a test runs with, and CI, which has none, runs the same.
    """
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_placeholder")
    monkeypatch.delenv("CLERK_JWT_KEY", raising=False)
    monkeypatch.delenv("CLERK_AUTHORIZED_PARTIES", raising=False)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Empty the limiter's counters, which live in process memory.

    Without this the 10/minute cap is spent across the whole suite and later
    tests get a 429.
    """
    limiter.reset()
    yield
    limiter.reset()
