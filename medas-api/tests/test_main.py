"""Tests for the HTTP routes.

Every request here goes through httpx.ASGITransport rather than
fastapi.testclient.TestClient. TestClient runs the lifespan, and this app's
lifespan calls init_engine() and executes SELECT 1 -- which would turn each
of these into an integration test needing a live database. ASGITransport
drives the app directly and skips lifespan events entirely.
"""

import json
import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.exc import IntegrityError

import main
from database.database import get_session
from main import app

SERVER_VERSION = "18.0 (Debian 18.0-1)"

# The owning user is a query parameter; the body is just the message.
USER_ID = "7f3c9a21-4be8-4d0f-9c17-2a6e5b8d41f0"
NEW_MESSAGE = {"role": "user", "text": "What is my last episode?"}

# Who the seeded greeting is addressed to. start_conversation passes a literal
# name rather than resolving one for USER_ID, so this is not the caller.
SEEDED_NAME = "Mattia"


class FakeSession:
    """Stands in for AsyncSession: returns a canned scalar, records what ran."""

    def __init__(self, result: object = SERVER_VERSION) -> None:
        self.result = result
        self.error: Exception | None = None
        self.statements: list[str] = []
        self.committed = False

    async def scalar(self, statement, params=None) -> object:
        self.statements.append(str(statement))
        if self.error is not None:
            raise self.error
        return self.result

    async def commit(self) -> None:
        self.committed = True


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# What the stubbed model answers with, so a test can assert on it.
CANNED_ANSWER = {
    "message": "Worth seeing your GP this week.",
    "severity": "S3",
    "confidence": "moderate",
}


@pytest.fixture(autouse=True)
def stub_the_assistant(monkeypatch) -> None:
    """Keep the model, the vector store and the record file out of the suite.

    Without this, creating a conversation reaches OpenRouter and Chroma: slow,
    billable, non-deterministic, and impossible in CI where neither exists.
    """

    async def _patient(session, user_id):
        return "name: Test Patient"

    # The Responses API shape: output is a list of items, and output_text is
    # the text of them joined. An empty output means "no tool call", which is
    # what ends the loop in main.
    response = SimpleNamespace(output=[], output_text=json.dumps(CANNED_ANSWER))

    monkeypatch.setattr(main, "patient_block", _patient)
    monkeypatch.setattr(main, "search_record", lambda *args, **kwargs: [])
    fake_client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **kwargs: response)
    )

    monkeypatch.setattr(main, "get_client", lambda: fake_client)


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


async def test_root_greets_the_user(client):
    response = await client.get("/", params={"user": "mattia"})

    assert response.status_code == 200
    assert response.json() == {
        "messages": [{"role": "assistant", "text": "Hi mattia, how can I help you?"}]
    }


async def test_root_requires_the_user_query_parameter(client):
    # `user` is a bare str with no default, so FastAPI makes it a required
    # query param. This pins that omitting it is a 422 and not a 500 -- and,
    # now that the seed lives at /, that a bare GET / is not a valid request.
    response = await client.get("/")

    assert response.status_code == 422


async def test_root_interpolates_the_user_verbatim(client):
    # The UI sends an opaque patient id rather than a display name, and
    # percent-encodes it on the way out. This pins that it survives the round
    # trip intact instead of arriving mangled into the greeting.
    user = "pat_7f3c9a21-4be8-4d0f-9c17-2a6e5b8d41f0"

    response = await client.get("/", params={"user": user})

    assert response.json()["messages"][0]["text"] == f"Hi {user}, how can I help you?"


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


async def test_add_message_returns_the_stored_message(client, fake_session):
    # A returned conversation_id is how append_message reports that a live row
    # matched, so this is the success path.
    fake_session.result = uuid.uuid4()
    conversation_id = uuid.uuid4()

    response = await client.post(
        f"/conversations/{conversation_id}/messages",
        json={"role": "user", "text": "What is my last episode?"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "user"
    assert body["text"] == "What is my last episode?"
    # Server-minted, so the caller learns them from the response.
    assert uuid.UUID(body["message_id"])
    assert body["timestamp"]
    assert fake_session.committed


async def test_add_message_to_a_missing_or_deleted_conversation_is_404(
    client, fake_session
):
    # No conversation_id back means the WHERE matched nothing: unknown id, or
    # soft-deleted. Either way the append did not happen.
    fake_session.result = None

    response = await client.post(
        f"/conversations/{uuid.uuid4()}/messages",
        json={"role": "user", "text": "hello"},
    )

    assert response.status_code == 404
    assert not fake_session.committed


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"role": "system", "text": "hi"}, id="unknown-role"),
        pytest.param({"role": "user", "text": " "}, id="blank-text"),
        pytest.param({"role": "user"}, id="missing-text"),
        pytest.param({"text": "hi"}, id="missing-role"),
    ],
)
async def test_add_message_rejects_invalid_payloads(client, fake_session, payload):
    response = await client.post(
        f"/conversations/{uuid.uuid4()}/messages", json=payload
    )

    assert response.status_code == 422


async def test_add_message_ignores_a_client_supplied_message_id(client, fake_session):
    # The schema has no message_id field, so one in the body is dropped rather
    # than trusted -- pinning that a caller cannot choose its own id.
    fake_session.result = uuid.uuid4()
    forged = str(uuid.uuid4())

    response = await client.post(
        f"/conversations/{uuid.uuid4()}/messages",
        json={"role": "user", "text": "hi", "message_id": forged},
    )

    assert response.status_code == 201
    assert response.json()["message_id"] != forged


async def test_add_message_is_a_single_statement(client, fake_session):
    # The point of the design: one UPDATE, no SELECT-then-write. A second
    # statement here would mean a read-modify-write crept back in.
    fake_session.result = uuid.uuid4()

    await client.post(
        f"/conversations/{uuid.uuid4()}/messages",
        json={"role": "user", "text": "hi"},
    )

    assert len(fake_session.statements) == 1
    assert fake_session.statements[0].startswith("UPDATE conversations")
    # onupdate does not fire for raw SQL, so the statement must bump the
    # column itself or updated_at silently stops tracking the last message.
    assert "updated_at = now()" in fake_session.statements[0]


async def test_start_conversation_seeds_the_greeting_then_the_first_message(
    client, fake_session
):
    fake_session.result = uuid.uuid4()

    response = await client.post(
        "/conversations", params={"userId": USER_ID}, json=NEW_MESSAGE
    )

    assert response.status_code == 201
    body = response.json()
    # The id is the whole point: the client needs it for every later message.
    assert body["conversation_id"] == str(fake_session.result)
    greeting, first, answer = body["messages"]
    assert greeting["role"] == "assistant"
    assert greeting["text"] == f"Hi {SEEDED_NAME}, how can I help you?"
    assert (first["role"], first["text"]) == ("user", NEW_MESSAGE["text"])
    # And the assistant's reply to it, with the triage code it assigned.
    assert (answer["role"], answer["text"]) == ("assistant", CANNED_ANSWER["message"])
    assert answer["severity"] == "S3"
    # Both seeded messages are real messages, not bare role/text pairs.
    assert uuid.UUID(greeting["message_id"]) != uuid.UUID(first["message_id"])
    assert greeting["timestamp"] <= first["timestamp"]
    assert fake_session.committed


async def test_seeded_greeting_ignores_the_caller(client, fake_session):
    # / greets whoever asks; start_conversation greets a hardcoded name. So
    # the greeting the UI previews and the one stored under it differ, and
    # the user sees it change the moment they send. Pinned as it behaves --
    # this becomes an equality check once the name is resolved from userId.
    fake_session.result = uuid.uuid4()
    user = "pat_7f3c9a21-4be8-4d0f-9c17-2a6e5b8d41f0"

    previewed = await client.get("/", params={"user": user})
    created = await client.post(
        "/conversations", params={"userId": USER_ID}, json=NEW_MESSAGE
    )

    assert (
        created.json()["messages"][0]["text"]
        == f"Hi {SEEDED_NAME}, how can I help you?"
    )
    assert (
        created.json()["messages"][0]["text"] != previewed.json()["messages"][0]["text"]
    )


async def test_start_conversation_for_an_unknown_user_is_404(client, fake_session):
    # The user_id FK is what rejects this; unmapped it would surface as a 500.
    fake_session.error = IntegrityError("INSERT", {}, Exception("fk violation"))

    response = await client.post(
        "/conversations", params={"userId": USER_ID}, json=NEW_MESSAGE
    )

    assert response.status_code == 404
    assert not fake_session.committed


async def test_start_conversation_inserts_once_then_appends_the_answer(
    client, fake_session
):
    # Creating and seeding the first message is one statement: a row nobody
    # can reference yet needs no read-modify-write and no second trip. The
    # assistant's reply is a second, separate append.
    fake_session.result = uuid.uuid4()

    await client.post("/conversations", params={"userId": USER_ID}, json=NEW_MESSAGE)

    assert len(fake_session.statements) == 2
    assert fake_session.statements[0].startswith("INSERT INTO conversations")
    assert fake_session.statements[1].startswith("UPDATE conversations")


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(NEW_MESSAGE | {"role": "system"}, id="unknown-role"),
        pytest.param(NEW_MESSAGE | {"text": " "}, id="blank-text"),
        pytest.param({"text": "hi"}, id="missing-role"),
    ],
)
async def test_start_conversation_rejects_invalid_payloads(
    client, fake_session, payload
):
    response = await client.post(
        "/conversations", params={"userId": USER_ID}, json=payload
    )

    assert response.status_code == 422


async def test_start_conversation_requires_the_user_id_query_parameter(
    client, fake_session
):
    # userId is a bare str on the handler, so FastAPI makes it a required
    # query param. Omitting it is a 422 rather than an insert with no owner.
    response = await client.post("/conversations", json=NEW_MESSAGE)

    assert response.status_code == 422
    assert fake_session.statements == []
