import json
import os
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from openai import OpenAI
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agent.assistant_general_prompt import ASSISTANT_SYSTEM_PROMPT
from agent.patient import UnknownPatient, patient_block, record_id
from agent.search import search_record
from database.database import dispose_engine, get_session, init_engine
from model import append_message, create_conversation, greeting_text
from schema import MessageRequest, NewMessage

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")


@lru_cache
def get_client() -> OpenAI:
    """The model client, built on first use rather than at import.

    The SDK raises when the key is missing, so building it at import time
    meant importing this module required credentials -- which is why CI could
    not even collect the tests, let alone run them.
    """
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    )


# The codes the prompt defines. Anything else is not a triage decision this
# service made, whatever the model returned.
SEVERITIES = frozenset({"S1", "S2", "S3", "S4", "S5"})

# Shown when the model's reply cannot be read. It says what happened and what
# to do about it, rather than leaving the patient with an error.
ASSISTANT_UNAVAILABLE = (
    "I could not review your record just now, so I cannot tell you how urgent "
    "this is. Please contact your care team today, and call emergency services "
    "if you feel very unwell."
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # Fail loudly at boot rather than on the first request.
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


@app.post("/messages")
def create_message(message_request: MessageRequest):
    return {
        "user_name": message_request.user_name,
        "message": message_request.message,
    }


@app.get("/")
def init_user_profile(user: str):
    # Not persisted: this is the preview shown before the user says anything.
    # The stored copy is seeded by POST /conversations from the same text.
    return {"messages": [{"role": "assistant", "text": greeting_text(user)}]}


@app.post("/conversations", status_code=201)
async def start_conversation(message: NewMessage, userId: str, session: SessionDep):
    try:
        conversation_id, messages = await create_conversation(
            session,
            userId,
            "Mattia",
            message.role,
            message.text,
        )
    except IntegrityError as exc:
        # The only constraint here is the user_id FK.
        raise HTTPException(status_code=404, detail="User not found") from exc

    await session.commit()

    # Who the record belongs to, read from the database rather than assumed.
    try:
        patient = await patient_block(session, userId)
    except UnknownPatient as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc

    # Flat, because this is the Responses API: name and parameters sit at the
    # top level. Chat Completions nests the same fields under "function", and
    # each endpoint rejects the other's shape with a 400.
    tools = [
        {
            "type": "function",
            "name": "search_record",
            "description": "Get patient records.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The message to query for",
                    },
                    "patient_id": {
                        "type": "string",
                        "description": "The id of the patient to search for",
                    },
                },
                "required": ["text", "patient_id"],
            },
        },
    ]

    # Named apart from `messages`: that holds the conversation as stored, and
    # overwriting it here is what left the endpoint returning the model's
    # payload instead of the record.
    input_list = [
        {"role": "system", "content": ASSISTANT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"<patient>\n{patient}\n</patient>\n"
                f"<message>\n{message.text}\n</message>"
            ),
        },
    ]

    response = get_client().responses.create(
        model="openai/gpt-4o-mini",
        input=input_list,
        max_output_tokens=1500,
        # Without this the model sometimes wraps its object in a ```json
        # fence, which json.loads will not read.
        text={"format": {"type": "json_object"}},
        tools=tools,
    )

    # The model's own turn goes back in first: a function_call_output is
    # matched to its call by call_id, so the call it answers has to be there.
    input_list += response.output

    answered_a_call = False

    for item in response.output:
        if item.type == "function_call" and item.name == "search_record":
            arguments = json.loads(item.arguments)
            query_result = search_record(
                arguments.get("text", message.text),
                # Ours, never the model's: patient_id is generated text, and a
                # message claiming a different record id must not become a read
                # of somebody else's.
                record_id(userId),
            )

            input_list.append(
                {
                    "type": "function_call_output",
                    "call_id": item.call_id,
                    # A string, not a list: the field carries whatever the tool
                    # produced, and the API will not serialise it for us.
                    "output": json.dumps(query_result),
                }
            )
            answered_a_call = True

    # Only when the model actually asked for something. Calling again
    # unconditionally paid for a second round on every request and re-asked the
    # question with the first answer already in the input.
    if answered_a_call:
        response = get_client().responses.create(
            model="openai/gpt-4o-mini",
            input=input_list,
            # The same terms as the first round: a reply that is not JSON, or
            # is cut off mid-object, fails the parse below either way.
            max_output_tokens=1500,
            text={"format": {"type": "json_object"}},
            tools=tools,
        )
    # A model that replies in prose, or leaves a field out, is a normal
    # occurrence rather than an exception -- so a bad reply becomes a visible
    # fallback rather than a 500 the patient cannot act on.
    #
    # AttributeError is in the net as well: on this API there is no
    # response.choices, and reaching for it would be a 500 rather than a reply
    # the patient can act on.
    try:
        answer = json.loads(response.output_text or "")
        reply_text = answer["message"]
        severity = answer.get("severity")
        confidence = answer.get("confidence", "low")
    except json.JSONDecodeError, KeyError, TypeError, AttributeError:
        reply_text = ASSISTANT_UNAVAILABLE
        severity, confidence = None, "low"

    # S2 when the severity is missing or not one this service defines. Never a
    # lower code: a triage answer that could not be read must not imply the
    # symptom was mild.
    if severity not in SEVERITIES:
        severity = "S2"

    # Stored, not merely returned -- otherwise the question survives a reload
    # and the answer to it does not. The severity travels with the turn
    # because which triage code was given, and when, is the thing an audit
    # asks about later.
    reply = await append_message(
        session,
        conversation_id,
        "assistant",
        reply_text,
        extra={"severity": severity, "confidence": confidence},
    )
    await session.commit()

    # The conversation as recorded: the greeting, what was asked, and the
    # answer. The client renders what the record holds rather than assuming.
    return {"conversation_id": conversation_id, "messages": [*messages, reply]}


# Appends only. An unknown or soft-deleted id is a 404, never an implicit
# create: that would resurrect deleted threads and let a caller pick its own
# primary key. A client without an id starts one above instead.
@app.post("/conversations/{conversation_id}/messages", status_code=201)
async def add_message(
    conversation_id: uuid.UUID, new_message: NewMessage, session: SessionDep
):
    message = await append_message(
        session, conversation_id, new_message.role, new_message.text
    )
    if message is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await session.commit()
    print(message)
    return message


@app.get("/health/db")
async def health_db(session: SessionDep):
    version = await session.scalar(text("SHOW server_version"))
    return {"status": "ok", "server_version": version}
