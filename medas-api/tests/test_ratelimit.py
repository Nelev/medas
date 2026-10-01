"""The per-route rate limit: 10 a minute, counted per user."""

import uuid

import httpx
import pytest
from starlette.requests import Request

from auth import current_user
from database.database import get_session
from main import app
from ratelimit import rate_limit_key


def as_user(user_key: str) -> dict[str, str]:
    return {"X-User": user_key}


def signed_in_as_header(request: Request) -> uuid.UUID:
    """Stands in for current_user, leaving the key where session_claims does."""
    request.state.user_key = request.headers["x-user"]
    return uuid.uuid4()


@pytest.fixture
async def client(monkeypatch):
    async def no_messages(*_):
        return []

    monkeypatch.setattr("main.get_conversation", no_messages)
    app.dependency_overrides[current_user] = signed_in_as_header
    app.dependency_overrides[get_session] = lambda: None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c
    app.dependency_overrides.clear()


async def test_the_eleventh_request_in_a_minute_is_429(client):
    statuses = [
        (
            await client.get(
                "/conversations/" + str(uuid.uuid4()), headers=as_user("u1")
            )
        ).status_code
        for _ in range(11)
    ]
    assert statuses[-1] == 429
    assert 429 not in statuses[:10]


async def test_each_user_has_their_own_bucket(client):
    for _ in range(10):
        await client.get("/conversations/" + str(uuid.uuid4()), headers=as_user("u1"))
    other = await client.get(
        "/conversations/" + str(uuid.uuid4()), headers=as_user("u2")
    )
    assert other.status_code != 429


def request_with(user_key: str | None) -> Request:
    request = Request({"type": "http", "headers": [], "client": ("9.9.9.9", 1)})
    if user_key:
        request.state.user_key = user_key
    return request


def test_key_is_the_verified_user():
    assert rate_limit_key(request_with("u1")) == "u1"


def test_key_falls_back_to_the_address_when_signed_out():
    assert rate_limit_key(request_with(None)) == "9.9.9.9"
