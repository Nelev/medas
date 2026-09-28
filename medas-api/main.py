import json
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agent.patient import record_id
from auth import CurrentUser, GreetingName, get_auth_settings
from database.database import dispose_engine, get_session, init_engine
from langchain_agent.agent import answer as ask_agent
from model import (
    MessageRole,
    append_message,
    create_conversation,
    greeting_text,
    list_messages,
)
from schema import NewMessage

# No model client is built here: the agent reads OPENROUTER_API_KEY from the
# environment when its graph is built, on the first request that needs it.
load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # Fail loudly at boot rather than on the first request: a missing
    # CLERK_SECRET_KEY stops the app here instead of turning every request
    # into a 500.
    get_auth_settings()
    engine = init_engine()
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))

    yield

    await dispose_engine()


app = FastAPI(lifespan=lifespan)

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# No CORS middleware: the browser never calls this API directly. The UI's
# requests go through its own server, so every caller here is server-side
# and same-origin rules do not apply.


@app.get("/")
def init_user_profile(_: CurrentUser, name: GreetingName):
    # Not persisted: this is the preview shown before the user says anything.
    # The stored copy is seeded by POST /ask from the same text. Signed in or
    # nothing, like every other route here.
    return {"messages": [{"role": "assistant", "text": greeting_text(name)}]}


def _as_turns(messages: list[dict], question: str) -> list[dict]:
    """The stored turns and the new question, as a chat model takes them.

    The wire calls the field `text`; a chat model calls it `content`. Roles
    are already "user" and "assistant" on both sides. No system turn: the
    prompt belongs to the agent, and a second copy would be sent twice.
    """
    return [
        *({"role": m["role"], "content": m["text"]} for m in messages),
        {"role": "user", "content": question},
    ]


async def _answer_and_store(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    turns: list[dict],
) -> dict:
    """Ask the agent, and store what it answers.

    Both paths through /ask end here, so the opening turn of a conversation
    and every later one are answered on the same terms.

    The prompt asks for one JSON object, so the reply is read as one: the
    patient sees `message`, and the triage code travels with the turn as
    metadata because which code was given, and when, is what an audit asks
    about later.
    """
    # The record searched is the signed-in user's, by the pat_{users.id}
    # convention agent/patient.py owns.
    reply = await ask_agent(turns, record_id=record_id(user_id))

    try:
        answer = json.loads(reply)
        reply_text = answer["message"]
        extra = {
            "severity": answer.get("severity"),
            "confidence": answer.get("confidence"),
        }
    except json.JSONDecodeError, KeyError, TypeError:
        # Prose where an object was asked for. The model does this on its own
        # judgement -- most often on a red flag, where it drops the format and
        # writes the warning out directly. That reply is a good answer, so it
        # is shown as it stands; only the triage code is lost with it.
        reply_text = reply
        extra = {}

    return await append_message(
        session,
        conversation_id,
        MessageRole.ASSISTANT,
        reply_text,
        extra=extra,
        user_id=user_id,
    )


@app.post("/ask", status_code=201)
async def ask(
    message: NewMessage,
    user_id: CurrentUser,
    session: SessionDep,
    name: GreetingName,
    conversationId: uuid.UUID | None = None,
):
    """Ask the agent. Starts a conversation when there is not one yet.

    One endpoint for every question, because the only difference between the
    first and the rest is whether a thread exists to hang it on -- and a
    caller that has just opened the app should not have to know that.

    conversationId is a query parameter rather than a path segment because a
    path segment cannot be absent, and rather than a body field because the
    body is a message and this is not part of one.

    Memory comes from the messages table rather than a LangGraph checkpointer.
    One store of a conversation, not two: a checkpointer would keep its own
    copy of the thread, and the copy the UI renders is this one.

    Who is asking comes from the session token, never from the request, and
    a conversationId that is not theirs is answered exactly like one that
    does not exist: 404, so an id cannot be probed for.

    The name the greeting addresses comes from the session token too, read
    only when a conversation is started.
    """
    if conversationId is None:
        try:
            conversation_id, written = await create_conversation(
                session,
                user_id,
                name,
                message.role,
                message.text,
            )
        except IntegrityError as exc:
            # The only constraint here is the user_id FK. current_user has
            # just found the row, so this is a user deleted since.
            raise HTTPException(status_code=404, detail="User not found") from exc

        await session.commit()

        # `written` is the greeting and the question, in that order, so
        # written[:-1] is everything the patient has seen before the question
        # being answered.
        turns = _as_turns(written[:-1], message.text)
    else:
        conversation_id = conversationId

        # Read before the new turn is written, so the model is not shown the
        # question it is being asked twice.
        #
        # Empty means the conversation is unknown or soft-deleted: a live one
        # always holds at least the greeting it was seeded with. Same signal
        # GET /conversations/{id} relies on.
        stored_messages = await list_messages(session, conversation_id, user_id=user_id)

        if not stored_messages:
            raise HTTPException(status_code=404, detail="Conversation not found")

        turns = _as_turns(stored_messages, message.text)

        sent = await append_message(
            session, conversation_id, message.role, message.text, user_id=user_id
        )

        if sent is None:
            # Live a moment ago and not now. The write is the only authority.
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Committed before the model call, so a run of several round trips
        # does not hold a write transaction open for its duration.
        await session.commit()

        written = [sent]

    reply = await _answer_and_store(session, conversation_id, user_id, turns)
    await session.commit()

    # Everything this request added to the thread: on a new conversation the
    # greeting, the question and the answer; on a later one the question and
    # the answer. The client appends them to what it already has.
    return {"conversation_id": conversation_id, "messages": [*written, reply]}


@app.get("/conversations/{conversation_id}")
async def read_conversation(
    conversation_id: uuid.UUID, user_id: CurrentUser, session: SessionDep
):
    messages = await list_messages(session, conversation_id, user_id=user_id)

    if not messages:
        # A live conversation always holds at least the greeting it was
        # seeded with, so nothing back means unknown, soft-deleted or someone
        # else's -- the same answer, for the same reason, that appending
        # gives.
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {"conversation_id": conversation_id, "messages": messages}


@app.get("/health/db")
async def health_db(session: SessionDep):
    version = await session.scalar(text("SHOW server_version"))
    return {"status": "ok", "server_version": version}
