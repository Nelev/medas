import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import dispose_engine, get_session, init_engine
from model import append_message, create_conversation, greeting_text
from schema import MessageRequest, NewConversation, NewMessage


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
async def start_conversation(new_conversation: NewConversation, session: SessionDep):
    try:
        conversation_id, messages = await create_conversation(
            session,
            new_conversation.user_id,
            new_conversation.user,
            new_conversation.role,
            new_conversation.text,
        )
    except IntegrityError as exc:
        # The only constraint here is the user_id FK.
        raise HTTPException(status_code=404, detail="User not found") from exc

    await session.commit()
    # Both seeded messages, so the client renders what was actually stored
    # rather than assuming its own copy of the greeting matches.
    return {"conversation_id": conversation_id, "messages": messages}


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
