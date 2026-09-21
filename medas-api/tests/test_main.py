"""Tests for the HTTP routes.

Every request here goes through httpx.ASGITransport rather than
fastapi.testclient.TestClient. TestClient runs the lifespan, and this app's
lifespan calls init_engine() and executes SELECT 1 -- which would turn each
of these into an integration test needing a live database. ASGITransport
drives the app directly and skips lifespan events entirely.
"""

import datetime
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

# An arbitrary fixed instant for the stored rows. Fixed, so a timestamp
# assertion fails for a real reason rather than a slow test.
EPOCH = datetime.datetime(2026, 9, 21, 9, 0, tzinfo=datetime.UTC)


class FakeResult(list):
    """The little of what AsyncSession.execute() returns that the model uses."""

    def first(self) -> SimpleNamespace | None:
        return self[0] if self else None


class FakeSession:
    """Stands in for AsyncSession: answers each statement, records what ran.

    Enough of a database to be worth asserting against. It mints ids and
    timestamps on write and hands the same rows back on read, because that is
    now where both come from -- the model no longer builds a message in
    Python and echoes it, it reads back what was stored.
    """

    def __init__(self) -> None:
        self.conversation_id = uuid.uuid4()
        # Whether the conversation an append or a read names is live. False
        # stands for unknown *and* for soft-deleted: the WHERE clause matches
        # nothing either way, which is exactly why one 404 covers both.
        self.matched = True
        self.error: Exception | None = None
        self.statements: list[str] = []
        self.parameters: list[dict | None] = []
        self.stored: list[SimpleNamespace] = []
        self.committed = False

    def _record(self, statement, params) -> None:
        self.statements.append(str(statement))
        self.parameters.append(params)
        if self.error is not None:
            raise self.error

    def _store(self, role: str, content: str, meta: dict | None = None):
        row = SimpleNamespace(
            message_id=uuid.uuid4(),
            # A plain string, as the enum column comes back.
            role=str(role),
            content=content,
            meta=meta or {},
            # Distinct and increasing, like clock_timestamp(). Sharing one
            # instant would make an ordering assertion pass for free.
            created_at=EPOCH + datetime.timedelta(seconds=len(self.stored)),
        )
        self.stored.append(row)
        return row

    async def scalar(self, statement, params=None) -> object:
        self._record(statement, params)
        if str(statement).startswith("INSERT INTO conversations"):
            return self.conversation_id
        return SERVER_VERSION

    async def execute(self, statement, params=None) -> FakeResult:
        self._record(statement, params)
        sql = str(statement)

        if sql.startswith("WITH m AS (INSERT INTO messages"):
            if not self.matched:
                return FakeResult()
            return FakeResult(
                self._store(role, content, json.loads(meta))
                for role, content, meta in zip(
                    params["roles"], params["contents"], params["metas"], strict=True
                )
            )

        return FakeResult(self.stored if self.matched else [])

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

    async def _search(*args, **kwargs):
        return []

    # Coroutine functions, because the route awaits both: a plain lambda here
    # returns a value the route would then try to await.
    async def _create(**kwargs):
        return response

    monkeypatch.setattr(main, "patient_block", _patient)
    monkeypatch.setattr(main, "search_record", _search)
    fake_client = SimpleNamespace(responses=SimpleNamespace(create=_create))

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
    conversation_id = uuid.uuid4()

    response = await client.post(
        f"/conversations/{conversation_id}/messages",
        json={"role": "user", "text": "What is my last episode?"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "user"
    assert body["text"] == "What is my last episode?"
    # Minted by the database, so the caller learns them from the response.
    assert uuid.UUID(body["message_id"])
    assert body["timestamp"]
    assert fake_session.committed


async def test_add_message_to_a_missing_or_deleted_conversation_is_404(
    client, fake_session
):
    # Nothing returned means the INSERT ... SELECT selected nothing: unknown
    # id, or soft-deleted. Either way the row was never written.
    fake_session.matched = False

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
    forged = str(uuid.uuid4())

    response = await client.post(
        f"/conversations/{uuid.uuid4()}/messages",
        json={"role": "user", "text": "hi", "message_id": forged},
    )

    assert response.status_code == 201
    assert response.json()["message_id"] != forged


async def test_add_message_is_a_single_statement(client, fake_session):
    # The point of the design: one INSERT, and no SELECT before it. The
    # conversation being live is checked inside the statement that writes, so
    # there is no window between deciding to write and writing.
    await client.post(
        f"/conversations/{uuid.uuid4()}/messages",
        json={"role": "user", "text": "hi"},
    )

    assert len(fake_session.statements) == 1
    statement = fake_session.statements[0]
    assert statement.startswith("WITH m AS (INSERT INTO messages")
    assert "FROM conversations c" in statement
    assert "NOT c.deleted" in statement


async def test_add_message_stores_no_metadata_of_its_own(client, fake_session):
    # A user turn carries nothing extra, and the column is NOT NULL: an empty
    # object, never None, or the insert fails.
    await client.post(
        f"/conversations/{uuid.uuid4()}/messages",
        json={"role": "user", "text": "hi"},
    )

    assert json.loads(fake_session.parameters[0]["metas"][0]) == {}


async def test_start_conversation_seeds_the_greeting_then_the_first_message(
    client, fake_session
):
    response = await client.post(
        "/conversations", params={"userId": USER_ID}, json=NEW_MESSAGE
    )

    assert response.status_code == 201
    body = response.json()
    # The id is the whole point: the client needs it for every later message.
    assert body["conversation_id"] == str(fake_session.conversation_id)
    greeting, first, answer = body["messages"]
    assert greeting["role"] == "assistant"
    assert greeting["text"] == f"Hi {SEEDED_NAME}, how can I help you?"
    assert (first["role"], first["text"]) == ("user", NEW_MESSAGE["text"])
    # And the assistant's reply to it, with the triage code it assigned.
    assert (answer["role"], answer["text"]) == ("assistant", CANNED_ANSWER["message"])
    assert answer["severity"] == "S3"
    # Both seeded messages are real messages, not bare role/text pairs.
    assert uuid.UUID(greeting["message_id"]) != uuid.UUID(first["message_id"])
    # Strictly earlier: the rows are written in one transaction, so a
    # transaction-start timestamp would make these equal and leave the two
    # messages with no order between them.
    assert greeting["timestamp"] < first["timestamp"]
    assert fake_session.committed


async def test_the_assistants_severity_is_stored_as_metadata(client, fake_session):
    # Not flattened into the message: it travels in the metadata column, so a
    # field added there later cannot collide with a column name.
    await client.post("/conversations", params={"userId": USER_ID}, json=NEW_MESSAGE)

    assert json.loads(fake_session.parameters[2]["metas"][0]) == {
        "severity": "S3",
        "confidence": "moderate",
    }


async def test_seeded_greeting_ignores_the_caller(client, fake_session):
    # / greets whoever asks; start_conversation greets a hardcoded name. So
    # the greeting the UI previews and the one stored under it differ, and
    # the user sees it change the moment they send. Pinned as it behaves --
    # this becomes an equality check once the name is resolved from userId.
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


async def test_start_conversation_writes_the_conversation_then_its_messages(
    client, fake_session
):
    # Three statements: the conversation, both seeded messages together, and
    # the assistant's reply. The seed is one statement rather than one per
    # message; the reply is separate because the model had not answered yet.
    await client.post("/conversations", params={"userId": USER_ID}, json=NEW_MESSAGE)

    assert len(fake_session.statements) == 3
    assert fake_session.statements[0].startswith("INSERT INTO conversations")
    for statement in fake_session.statements[1:]:
        assert statement.startswith("WITH m AS (INSERT INTO messages")
        # The greeting precedes the question because seq says so, not because
        # RETURNING happened to emit the rows that way -- it has no order.
        assert statement.endswith("ORDER BY m.seq")


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


async def test_read_conversation_returns_the_whole_history(client, fake_session):
    # What the jsonb array could only give all at once, and what nothing could
    # give at all: the conversation, read back after the fact.
    created = await client.post(
        "/conversations", params={"userId": USER_ID}, json=NEW_MESSAGE
    )
    conversation_id = created.json()["conversation_id"]

    response = await client.get(f"/conversations/{conversation_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == conversation_id
    assert [m["text"] for m in body["messages"]] == [
        f"Hi {SEEDED_NAME}, how can I help you?",
        NEW_MESSAGE["text"],
        CANNED_ANSWER["message"],
    ]
    # Metadata comes back merged into the message, the shape it had when it
    # lived in the array -- so the UI reads a stored turn the same way it
    # reads a fresh one.
    assert body["messages"][2]["severity"] == "S3"


async def test_read_a_missing_or_deleted_conversation_is_404(client, fake_session):
    # No rows back. Unknown id, or soft-deleted -- the messages of a deleted
    # conversation are still rows, and the join to conversations is what
    # hides them. One answer for both, which is the right one to give a
    # caller guessing at uuids. A live conversation always holds at least the
    # greeting it was seeded with, so empty never means an empty conversation.
    response = await client.get(f"/conversations/{uuid.uuid4()}")

    assert response.status_code == 404
