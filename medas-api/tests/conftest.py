"""Shared fixtures.

Everything here exists to undo process-wide state that would otherwise leak
between tests.
"""

import pytest

from database.settings import get_settings


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """Drop the lru_cache around get_settings.

    Without this the first test to call get_settings() freezes the result for
    the whole session, so a later test that patches the environment silently
    reads the earlier test's settings.
    """
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
