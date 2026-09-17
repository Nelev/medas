"""Tests for the HTTP routes.

Every request here goes through httpx.ASGITransport rather than
fastapi.testclient.TestClient. TestClient runs the lifespan, and this app's
lifespan calls init_engine() and executes SELECT 1 -- which would turn each
of these into an integration test needing a live database. ASGITransport
drives the app directly and skips lifespan events entirely.
"""

from collections.abc import AsyncIterator

import httpx
import pytest

from database.database import get_session
from main import app

SERVER_VERSION = "18.0 (Debian 18.0-1)"


class FakeSession:
    """Stands in for AsyncSession for the one call health_db makes."""

    def __init__(self, version: str = SERVER_VERSION) -> None:
        self.version = version
        self.statements: list[str] = []

    async def scalar(self, statement) -> str:
        self.statements.append(str(statement))
        return self.version


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def fake_session() -> AsyncIterator[FakeSession]:
    """Override the session dependency, and undo it afterwards.

    dependency_overrides is module-level state on the app object, so a test
    that sets it without clearing leaks the override into every later test.
    """
    session = FakeSession()

    async def _override() -> AsyncIterator[FakeSession]:
        yield session

    app.dependency_overrides[get_session] = _override
    yield session
    app.dependency_overrides.clear()


async def test_root_returns_the_greeting(client):
    response = await client.get("/")

    assert response.status_code == 200
    assert response.json() == {"Hello": "World"}


async def test_create_message_echoes_the_payload(client):
    response = await client.post(
        "/messages", json={"message": "What is my last episode?", "user_name": "mattia"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "user_name": "mattia",
        "message": "What is my last episode?",
    }


async def test_create_message_strips_surrounding_whitespace(client):
    response = await client.post(
        "/messages", json={"message": "  hello  ", "user_name": "  mattia  "}
    )

    assert response.status_code == 200
    assert response.json() == {"user_name": "mattia", "message": "hello"}


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"message": "", "user_name": "m"}, id="empty-message"),
        pytest.param({"message": " ", "user_name": "m"}, id="blank-message"),
        pytest.param({"message": "hi", "user_name": " "}, id="blank-user-name"),
        pytest.param({"message": "hi"}, id="missing-user-name"),
        pytest.param({"user_name": "m"}, id="missing-message"),
        pytest.param({}, id="empty-body"),
    ],
)
async def test_create_message_rejects_invalid_payloads(client, payload):
    # The schema is tested directly in test_schema.py; this pins that the
    # rejection actually surfaces as a 422 over HTTP rather than a 500.
    response = await client.post("/messages", json=payload)

    assert response.status_code == 422


async def test_create_message_rejects_a_non_string_message(client):
    response = await client.post("/messages", json={"message": 42, "user_name": "m"})

    assert response.status_code == 422


async def test_health_db_reports_the_server_version(client, fake_session):
    response = await client.get("/health/db")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "server_version": SERVER_VERSION}


async def test_health_db_queries_the_server_version(client, fake_session):
    await client.get("/health/db")

    assert fake_session.statements == ["SHOW server_version"]


async def test_unknown_route_is_a_404(client):
    response = await client.get("/does-not-exist")

    assert response.status_code == 404
