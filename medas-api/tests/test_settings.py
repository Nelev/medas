"""Tests for database settings and the DSN they build."""

import pytest
from pydantic import SecretStr, ValidationError

from database.settings import DbSettings, get_settings

# Every construction below passes _env_file=None. DbSettings reads .env from
# the working directory by default, so without this a test result depends on
# an untracked file that differs per machine.
PASSWORD = SecretStr("s3cret")


def make_settings(**overrides) -> DbSettings:
    overrides.setdefault("database_password", PASSWORD)
    return DbSettings(_env_file=None, **overrides)


def test_password_is_the_only_required_field():
    settings = make_settings()
    assert settings.database_host == "localhost"
    assert settings.database_port == 5432
    assert settings.database_user == "medas"
    assert settings.database_name == "medas"


def test_missing_password_is_a_validation_error():
    # No default, so an absent password fails at construction rather than
    # producing a DSN that cannot authenticate.
    with pytest.raises(ValidationError):
        DbSettings(_env_file=None)


def test_pool_defaults():
    settings = make_settings()
    assert settings.db_echo is False
    assert settings.db_pool_size == 5
    assert settings.db_max_overflow == 5
    assert settings.db_pool_timeout == 10


def test_dsn_uses_the_async_driver():
    # asyncpg, not psycopg: psycopg3's async mode cannot run on the Windows
    # ProactorEventLoop that uvicorn gets by default.
    assert make_settings().database_url.drivername == "postgresql+asyncpg"


def test_dsn_carries_every_component():
    settings = make_settings(
        database_host="db.internal",
        database_port=6543,
        database_user="someone",
        database_name="medas_test",
    )
    url = settings.database_url
    assert url.host == "db.internal"
    assert url.port == 6543
    assert url.username == "someone"
    assert url.database == "medas_test"


def test_password_reserved_characters_are_escaped_in_the_rendered_dsn():
    # URL.create stores the password raw and escapes on render, so characters
    # that would otherwise split the DSN need no hand-encoding by the caller.
    settings = make_settings(database_password=SecretStr("p@ss:w/rd%"))
    url = settings.database_url

    assert url.password == "p@ss:w/rd%"
    assert "p%40ss%3Aw%2Frd%25" in url.render_as_string(hide_password=False)


def test_rendered_dsn_hides_the_password_by_default():
    settings = make_settings(database_password=SecretStr("hunter2"))
    rendered = settings.database_url.render_as_string()

    assert "hunter2" not in rendered
    assert "***" in rendered


def test_secret_does_not_leak_through_repr():
    # SecretStr is what keeps the password out of tracebacks and logs.
    settings = make_settings(database_password=SecretStr("hunter2"))

    assert "hunter2" not in str(settings)
    assert "hunter2" not in repr(settings)


def test_get_settings_is_cached(monkeypatch):
    # Callers treat settings as a singleton; the cache is what makes that
    # true. The autouse fixture in conftest clears it between tests.
    #
    # The password comes from the environment rather than .env: this is the
    # one test that goes through get_settings(), which reads the real file,
    # and CI has no .env to read.
    monkeypatch.setenv("DATABASE_PASSWORD", "s3cret")

    assert get_settings() is get_settings()
