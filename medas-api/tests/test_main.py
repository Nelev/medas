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

import controller.conversation
import controller.documents
from auth import current_user, greeting_name
from controller.conversation import UNAVAILABLE_REPLY
from database.database import get_session
from main import app
from model import greeting_texts
from schema import AgentUnavailable

SERVER_VERSION = "18.0 (Debian 18.0-1)"

# Who every request is from: current_user is overridden to return it, so
# the routes are tested apart from token verification (tests/test_auth.py).
USER_ID = uuid.UUID("7f3c9a21-4be8-4d0f-9c17-2a6e5b8d41f0")
NEW_MESSAGE = {"role": "user", "text": "What is my last episode?"}

# The assistant's opening turns unless a test names someone: the client is an
# account without a first name.
GREETING = greeting_texts(None)

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
        # The user's conversation ids, newest first, as the list query
        # returns them.
        self.conversations: list[uuid.UUID] = []
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

        if sql.startswith("SELECT conversation_id FROM conversations"):
            return FakeResult(
                SimpleNamespace(conversation_id=c) for c in self.conversations
            )

        return FakeResult(self.stored if self.matched else [])

    async def commit(self) -> None:
        self.committed = True


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """A client signed in as USER_ID.

    current_user and greeting_name are overridden rather than a token sent,
    so no route test depends on Clerk; the overrides go with the rest on
    teardown.
    """
    app.dependency_overrides[current_user] = lambda: USER_ID
    app.dependency_overrides[greeting_name] = lambda: None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def signed_out(client) -> None:
    """Undo the client's sign-in, so the real current_user runs."""
    del app.dependency_overrides[current_user]


def named(name: str) -> None:
    """Sign the client in as an account with this first name."""
    app.dependency_overrides[greeting_name] = lambda: name


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


async def test_root_greets_the_user(client, fake_session):
    named("mattia")

    response = await client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "messages": [
            {"role": "assistant", "text": text} for text in greeting_texts("mattia")
        ],
        "conversations": [],
    }


async def test_root_lists_the_users_conversations(client, fake_session):
    newer, older = uuid.uuid4(), uuid.uuid4()
    fake_session.conversations = [newer, older]

    response = await client.get("/")

    # In the order the query returns them, newest first.
    assert response.json()["conversations"] == [
        {"conversation_id": str(newer)},
        {"conversation_id": str(older)},
    ]
    # Scoped to the signed-in user in the statement itself, live ones only.
    assert fake_session.parameters[-1] == {"user_id": USER_ID}
    assert "NOT deleted" in fake_session.statements[-1]


async def test_root_without_a_name_greets_there(client, fake_session):
    response = await client.get("/")

    assert [m["text"] for m in response.json()["messages"]] == GREETING
    assert GREETING[0].startswith("Hi there,")


# What the stubbed agent answers with. Text, because that is what the agent
# returns: the reply is the last message of the run.
AGENT_REPLY = "Worth seeing your GP this week."


class AgentCalls(list):
    """The turns of each agent call, with the record each was to search."""

    def __init__(self) -> None:
        super().__init__()
        self.record_ids: list[str] = []


@pytest.fixture(autouse=True)
def stub_the_agent(monkeypatch):
    """Answer every route that calls the agent, without reaching OpenRouter.

    Autouse, and the only seam there is: every question goes through /ask and
    then ask_agent, so stubbing it keeps the model, the tool and the vector
    store out of the suite entirely. Without it the suite would be slow, billable,
    non-deterministic, and impossible in CI where neither the model nor
    Chroma exists.

    Records the turns it was given, so a test can assert on what the agent
    was told, and in `record_ids` which record each call was to search.
    """
    calls = AgentCalls()

    async def _answer(turns, *, record_id, attachments=()):
        calls.append(turns)
        calls.record_ids.append(record_id)
        return AGENT_REPLY

    monkeypatch.setattr(controller.conversation, "ask_agent", _answer)

    return calls


async def test_a_json_reply_is_read_for_its_message_and_triage_code(
    client, fake_session, monkeypatch
):
    """The shape the prompt actually asks for.

    The patient reads `message`; the code rides along as metadata, which is
    what the badge renders from and what an audit reads later.
    """

    async def _json_answer(turns, *, record_id, attachments=()):
        return json.dumps(
            {
                "message": "Worth seeing your GP this week.",
                "severity": "S3",
                "confidence": "moderate",
                "safety_net": "Come back sooner if it worsens.",
            }
        )

    monkeypatch.setattr(controller.conversation, "ask_agent", _json_answer)
    fake_session._store("assistant", "Hi Mattia, how can I help you?")

    response = await client.post(
        "/ask",
        params={"conversationId": uuid.uuid4()},
        json={"role": "user", "text": "My chest hurts."},
    )

    reply = response.json()["messages"][1]

    # The message, not the object it arrived in.
    assert reply["text"] == "Worth seeing your GP this week."
    assert reply["severity"] == "S3"
    assert reply["confidence"] == "moderate"
    # Only the two the route reads. The prompt's other fields are answered and
    # discarded, which is a choice worth noticing if one of them is ever
    # wanted.
    assert "safety_net" not in reply


async def test_a_prose_reply_is_kept_as_the_answer(
    client, fake_session, stub_the_agent
):
    """The model drops the format on its own judgement, most often on a red
    flag -- and that reply is a good answer, so it is shown rather than
    discarded. Only the triage code is lost with it.
    """
    fake_session._store("assistant", "Hi Mattia, how can I help you?")

    response = await client.post(
        "/ask",
        params={"conversationId": uuid.uuid4()},
        json={"role": "user", "text": "My chest hurts."},
    )

    reply = response.json()["messages"][1]

    assert reply["text"] == AGENT_REPLY
    assert "severity" not in reply


async def test_ask_when_the_agent_fails_is_503_and_keeps_a_reply(
    client, fake_session, monkeypatch
):
    async def _fail(turns, *, record_id, attachments=()):
        raise AgentUnavailable

    monkeypatch.setattr(controller.conversation, "ask_agent", _fail)
    fake_session._store("assistant", "Hi Mattia, how can I help you?")

    response = await client.post(
        "/ask",
        params={"conversationId": uuid.uuid4()},
        json={"role": "user", "text": "My chest hurts."},
    )

    assert response.status_code == 503
    assert fake_session.committed
    assert fake_session.stored[-1].content == UNAVAILABLE_REPLY


async def test_ask_stores_the_question_and_the_answer(
    client, fake_session, stub_the_agent
):
    # A turn already on the record, so the conversation reads as live.
    fake_session._store("assistant", "Hi Mattia, how can I help you?")

    response = await client.post(
        "/ask",
        params={"conversationId": uuid.uuid4()},
        json={"role": "user", "text": "Can I take ibuprofen?"},
    )

    assert response.status_code == 201
    sent, reply = response.json()["messages"]
    assert (sent["role"], sent["text"]) == ("user", "Can I take ibuprofen?")
    assert (reply["role"], reply["text"]) == ("assistant", AGENT_REPLY)
    assert fake_session.committed


async def test_ask_passes_the_stored_history_to_the_agent(
    client, fake_session, stub_the_agent
):
    """The point of reading the table: the agent is told what was said before."""
    fake_session._store("assistant", "Hi Mattia, how can I help you?")
    fake_session._store("user", "I have been wheezing.")
    fake_session._store("assistant", "Since when?")

    await client.post(
        "/ask",
        params={"conversationId": uuid.uuid4()},
        json={"role": "user", "text": "Since Tuesday."},
    )

    # `content`, not `text`: the wire's name for the field is not the model's.
    # The prior turns, then the question -- and no system turn, which belongs
    # to the agent.
    # `content`, not `text`: the wire's name for the field is not the model's.
    # The stored turns, oldest first, then the question being asked.
    assert stub_the_agent == [
        [
            {"role": "assistant", "content": "Hi Mattia, how can I help you?"},
            {"role": "user", "content": "I have been wheezing."},
            {"role": "assistant", "content": "Since when?"},
            {"role": "user", "content": "Since Tuesday."},
        ]
    ]


async def test_ask_does_not_show_the_agent_the_question_twice(
    client, fake_session, stub_the_agent
):
    """History is read before the new turn is written, not after."""
    fake_session._store("assistant", "Hi Mattia, how can I help you?")

    await client.post(
        "/ask",
        params={"conversationId": uuid.uuid4()},
        json={"role": "user", "text": "Can I take ibuprofen?"},
    )

    asked = [
        turn for turn in stub_the_agent[0] if turn["content"] == "Can I take ibuprofen?"
    ]

    # Once, as the last turn -- not again in the history behind it.
    assert len(asked) == 1
    assert stub_the_agent[0][-1] == asked[0]


async def test_ask_sends_the_whole_thread(client, fake_session, stub_the_agent):
    """Every stored turn goes to the agent, oldest first, then the question.

    Nothing is dropped and nothing is windowed. Worth pinning as a choice
    rather than an accident: the transcript is re-sent on every model turn of
    a run, so a long thread costs more with every message in it.
    """
    for n in range(30):
        fake_session._store("user", f"turn {n}")

    await client.post(
        "/ask",
        params={"conversationId": uuid.uuid4()},
        json={"role": "user", "text": "and now?"},
    )

    turns = stub_the_agent[0]

    assert len(turns) == 31
    assert turns[0]["content"] == "turn 0"
    assert turns[-1]["content"] == "and now?"


async def test_ask_on_a_missing_or_deleted_conversation_is_404(
    client, fake_session, stub_the_agent
):
    fake_session.matched = False

    response = await client.post(
        "/ask",
        params={"conversationId": uuid.uuid4()},
        json={"role": "user", "text": "hello"},
    )

    assert response.status_code == 404
    # Nothing written, and the model never called.
    assert not fake_session.committed
    assert stub_the_agent == []


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"role": "user"}, id="missing-text"),
        pytest.param({"role": "user", "text": " "}, id="blank-text"),
        pytest.param({"role": "system", "text": "hi"}, id="unknown-role"),
        # A client must not write the model's side of the thread.
        pytest.param({"role": "assistant", "text": "I agree."}, id="assistant-role"),
    ],
)
async def test_ask_rejects_invalid_payloads(
    client, fake_session, stub_the_agent, payload
):
    # It reuses NewMessage, so it inherits that schema's validation rather
    # than restating it.
    response = await client.post(
        "/ask",
        params={"conversationId": uuid.uuid4()},
        json=payload,
    )

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


async def test_ask_with_an_id_does_not_start_another_conversation(
    client, fake_session, stub_the_agent
):
    """The fork the whole endpoint turns on.

    A conversationId means append to that thread. Creating one anyway would
    strand the thread the caller named and answer into a new one, which the
    client would only notice by the id changing under it.
    """
    fake_session._store("assistant", "Hi Mattia, how can I help you?")

    response = await client.post(
        "/ask",
        params={"conversationId": uuid.uuid4()},
        json={"role": "user", "text": "And my medications?"},
    )

    assert response.status_code == 201
    assert not any(
        statement.startswith("INSERT INTO conversations")
        for statement in fake_session.statements
    )
    # The question and the answer, without a greeting in front of them.
    assert len(response.json()["messages"]) == 2


async def test_ask_without_an_id_seeds_the_greeting_then_the_first_message(
    client, fake_session
):
    response = await client.post("/ask", json=NEW_MESSAGE)

    assert response.status_code == 201
    body = response.json()
    # The id is the whole point: the client needs it for every later message.
    assert body["conversation_id"] == str(fake_session.conversation_id)
    *greetings, first, answer = body["messages"]
    assert [(m["role"], m["text"]) for m in greetings] == [
        ("assistant", text) for text in GREETING
    ]
    greeting = greetings[-1]
    assert (first["role"], first["text"]) == ("user", NEW_MESSAGE["text"])
    # And the agent's reply to it.
    assert (answer["role"], answer["text"]) == ("assistant", AGENT_REPLY)
    # Both seeded messages are real messages, not bare role/text pairs.
    assert uuid.UUID(greeting["message_id"]) != uuid.UUID(first["message_id"])
    # Strictly earlier: the rows are written in one transaction, so a
    # transaction-start timestamp would make these equal and leave the two
    # messages with no order between them.
    assert greeting["timestamp"] < first["timestamp"]
    assert fake_session.committed


async def test_the_assistants_reply_carries_no_metadata(client, fake_session):
    # The agent answers in text, so there is no triage code to store. The
    # column is NOT NULL, so what goes in is an empty object, never None.
    await client.post("/ask", json=NEW_MESSAGE)

    written = [p for p in fake_session.parameters if p and "metas" in p]

    assert json.loads(written[-1]["metas"][0]) == {}


async def test_the_first_turn_is_answered_knowing_the_greeting(
    client, fake_session, stub_the_agent
):
    """Both routes tell the agent the same story about what the patient saw.

    The greeting is a turn the patient read, so the opening question is
    answered in its light -- exactly as a follow-up is. Asserted because the
    two routes could easily disagree about this and nothing would look wrong.
    """
    await client.post("/ask", json=NEW_MESSAGE)

    assert stub_the_agent == [
        [
            *[{"role": "assistant", "content": text} for text in GREETING],
            {"role": "user", "content": NEW_MESSAGE["text"]},
        ]
    ]


async def test_seeded_greeting_is_the_one_previewed(client, fake_session):
    # Both routes read the name from the same session, so the greeting stored
    # is the one the patient was already looking at -- it does not change
    # under them the moment they send.
    named("Ada")

    previewed = await client.get("/")
    created = await client.post("/ask", json=NEW_MESSAGE)

    previewed_turns = previewed.json()["messages"]
    stored = created.json()["messages"][: len(previewed_turns)]
    assert [(m["role"], m["text"]) for m in stored] == [
        (m["role"], m["text"]) for m in previewed_turns
    ]
    assert stored[0]["text"].startswith("Hi Ada,")


async def test_ask_without_an_id_for_an_unknown_user_is_404(client, fake_session):
    # The user_id FK is what rejects this; unmapped it would surface as a 500.
    fake_session.error = IntegrityError("INSERT", {}, Exception("fk violation"))

    response = await client.post("/ask", json=NEW_MESSAGE)

    assert response.status_code == 404
    assert not fake_session.committed


async def test_ask_without_an_id_writes_the_conversation_then_its_messages(
    client, fake_session
):
    # Three statements: the conversation, both seeded messages together, and
    # the assistant's reply. The seed is one statement rather than one per
    # message; the reply is separate because the model had not answered yet.
    await client.post("/ask", json=NEW_MESSAGE)

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
async def test_ask_without_an_id_rejects_invalid_payloads(
    client, fake_session, payload
):
    response = await client.post("/ask", json=payload)

    assert response.status_code == 422


async def test_ask_signed_out_is_401_and_touches_nothing(
    client, fake_session, signed_out
):
    response = await client.post("/ask", json=NEW_MESSAGE)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert fake_session.statements == []


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/"), ("GET", f"/conversations/{uuid.uuid4()}")],
)
async def test_every_other_route_is_401_signed_out(
    client, fake_session, signed_out, method, path
):
    response = await client.request(method, path)

    assert response.status_code == 401


PDF = {"file": ("record.pdf", b"%PDF-1.4", "application/pdf")}


@pytest.fixture
def has_record(monkeypatch):
    """The signed-in user has a record to upload into; the agent is stubbed."""
    monkeypatch.setattr(controller.documents, "find_record", lambda rid: {"id": rid})


async def test_an_upload_starts_a_conversation(
    client, fake_session, stub_the_agent, has_record
):
    response = await client.post("/documents", files=PDF)

    assert response.status_code == 201
    body = response.json()
    assert body["conversation_id"] == str(fake_session.conversation_id)
    assert [(m["role"], m["text"]) for m in body["messages"]] == [
        *[("assistant", text) for text in GREETING],
        ("user", "upload file requested: record.pdf"),
        ("assistant", AGENT_REPLY),
    ]
    # Asked about the file alone, not the conversation around it.
    assert "record.pdf" in stub_the_agent[0][-1]["content"]


async def test_an_upload_joins_the_conversation(client, fake_session, has_record):
    fake_session._store("assistant", "Hi Mattia, how can I help you?")

    response = await client.post(
        "/documents",
        params={"conversationId": str(fake_session.conversation_id)},
        files=PDF,
    )

    assert response.status_code == 201
    assert [(m["role"], m["text"]) for m in response.json()["messages"]] == [
        ("user", "upload file requested: record.pdf"),
        ("assistant", AGENT_REPLY),
    ]


async def test_documents_on_an_unknown_conversation_is_404(
    client, fake_session, has_record
):
    fake_session.matched = False

    response = await client.post(
        "/documents", params={"conversationId": str(uuid.uuid4())}, files=PDF
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Conversation not found"}


async def test_documents_signed_out_is_401(client, signed_out):
    response = await client.post("/documents", files=PDF)

    assert response.status_code == 401


async def test_health_stays_public(client, fake_session, signed_out):
    # What a load balancer polls; it knows no user and reads no record.
    response = await client.get("/health/db")

    assert response.status_code == 200


@pytest.mark.parametrize("conversation", [None, "existing"])
async def test_the_agent_searches_the_signed_in_users_record(
    client, fake_session, stub_the_agent, conversation
):
    # Both paths through /ask end in the same agent call, and both must hand
    # it the caller's record -- pat_ followed by their users.id.
    params = {}
    if conversation:
        fake_session._store("assistant", "Hi Mattia, how can I help you?")
        params["conversationId"] = uuid.uuid4()

    await client.post("/ask", params=params, json=NEW_MESSAGE)

    assert stub_the_agent.record_ids == [f"pat_{USER_ID}"]


@pytest.mark.parametrize(
    "params",
    [
        # The old contract, sent anyway: ignored rather than trusted.
        pytest.param({"userId": uuid.uuid4()}, id="userId"),
    ],
)
async def test_ask_takes_the_owner_from_the_session_not_the_query(
    client, fake_session, params
):
    # Nothing in the query can be used to write as someone else.
    await client.post("/ask", params=params, json=NEW_MESSAGE)

    owners = [p["user_id"] for p in fake_session.parameters if p and "user_id" in p]
    assert owners
    assert set(owners) == {USER_ID}


async def test_every_conversation_read_and_write_is_scoped_to_the_user(
    client, fake_session, stub_the_agent
):
    # The ownership check is one clause in each statement. Pinned on the
    # text as well as the parameters, so dropping the clause fails here even
    # though the fake would still bind a user_id nothing reads.
    fake_session._store("assistant", "Hi Mattia, how can I help you?")

    await client.post(
        "/ask",
        params={"conversationId": uuid.uuid4()},
        json={"role": "user", "text": "And my medications?"},
    )

    touching_messages = [
        (statement, params)
        for statement, params in zip(
            fake_session.statements, fake_session.parameters, strict=True
        )
        if "messages" in statement
    ]
    assert touching_messages
    for statement, params in touching_messages:
        assert "c.user_id = :user_id" in statement
        assert params["user_id"] == USER_ID


async def test_someone_elses_conversation_reads_as_missing(client, fake_session):
    # The statement matches nothing when the owner differs, which the fake
    # models as matching nothing at all: the same 404 as an unknown id, so
    # an id cannot be probed for.
    fake_session.matched = False

    response = await client.get(f"/conversations/{uuid.uuid4()}")

    assert response.status_code == 404


async def test_read_conversation_returns_the_whole_history(client, fake_session):
    # What the jsonb array could only give all at once, and what nothing could
    # give at all: the conversation, read back after the fact.
    created = await client.post("/ask", json=NEW_MESSAGE)
    conversation_id = created.json()["conversation_id"]

    response = await client.get(f"/conversations/{conversation_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == conversation_id
    assert [m["text"] for m in body["messages"]] == [
        *GREETING,
        NEW_MESSAGE["text"],
        AGENT_REPLY,
    ]
    # Metadata still comes back merged into the message, the shape it had when
    # it lived in the array -- there is simply nothing in it to merge.
    assert body["messages"][-1].keys() == {"role", "text", "message_id", "timestamp"}


async def test_read_a_missing_or_deleted_conversation_is_404(client, fake_session):
    # No rows back. Unknown id, or soft-deleted -- the messages of a deleted
    # conversation are still rows, and the join to conversations is what
    # hides them. One answer for both, which is the right one to give a
    # caller guessing at uuids. A live conversation always holds at least the
    # greeting it was seeded with, so empty never means an empty conversation.
    response = await client.get(f"/conversations/{uuid.uuid4()}")

    assert response.status_code == 404


async def test_an_oversized_upload_is_413_and_stores_nothing(
    client, fake_session, stub_the_agent, has_record
):
    big = b"%PDF-" + b"0" * controller.documents.MAX_UPLOAD_BYTES
    response = await client.post("/documents", files={"file": ("big.pdf", big)})

    assert response.status_code == 413
    assert not fake_session.committed
    assert stub_the_agent == []


async def test_a_non_pdf_upload_is_415_and_stores_nothing(
    client, fake_session, stub_the_agent, has_record
):
    response = await client.post(
        "/documents", files={"file": ("a.pdf", b"MZ not a pdf")}
    )

    assert response.status_code == 415
    assert not fake_session.committed
    assert stub_the_agent == []
