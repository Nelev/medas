"""The conversation model, and the one write that matters: adding a message."""

import datetime
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Uuid, bindparam, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base

__all__ = [
    "Conversation",
    "append_message",
    "create_conversation",
    "greeting_text",
]


class Conversation(Base):
    __tablename__ = "conversations"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # JSONB, not JSON: || below is a jsonb operator, and json would keep the
    # raw text and reparse it on every read.
    messages: Mapped[list[dict]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    deleted: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))

    # TIMESTAMPTZ, like users.updated_at. onupdate covers ORM/Core writes;
    # append_message is raw SQL, which bypasses it, so that statement sets the
    # column itself.
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


_CREATE = text(
    "INSERT INTO conversations (user_id, messages) VALUES (:user_id, :messages) "
    "RETURNING conversation_id"
).bindparams(bindparam("messages", type_=JSONB))


# One statement, so concurrent senders queue on the row lock instead of
# overwriting each other. A read-modify-write in Python would lose messages
# whenever two requests for the same conversation overlap.
_APPEND = text(
    "UPDATE conversations SET messages = messages || :message, updated_at = now() "
    "WHERE conversation_id = :conversation_id AND NOT deleted "
    "RETURNING conversation_id"
    # Typing the parameter is what makes || a jsonb append: it serialises the
    # list and renders the $1::JSONB cast. An inline ::jsonb in the SQL above
    # would instead stop SQLAlchemy recognising :message as a parameter at all.
).bindparams(bindparam("message", type_=JSONB))


def _new_message(role: str, message_text: str) -> dict:
    """Build one message.

    message_id and timestamp are minted here, never taken from the caller: a
    client-supplied id can collide with one already in the array, and a client
    clock skews ordering.
    """
    return {
        "role": role,
        "text": message_text,
        "message_id": str(uuid.uuid4()),
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
    }


def greeting_text(user: str) -> str:
    """The assistant's opening line.

    Shared, so the copy the UI renders before a conversation exists and the
    copy stored as its first message cannot drift apart.
    """
    return f"Hi {user}, how can I help you?"


async def create_conversation(
    session: AsyncSession,
    user_id: uuid.UUID,
    user: str,
    role: str,
    message_text: str,
) -> tuple[uuid.UUID, list[dict]]:
    """Start a conversation, seeded with the greeting and the first message.

    A plain INSERT, not the careful append below: the row does not exist yet,
    so nobody else can be writing to it. Raises IntegrityError if user_id is
    not a real user -- the FK is the check.

    The greeting is built here rather than accepted from the caller: assistant
    turns are the server's to write, or a client could put words in its mouth.
    """
    messages = [
        _new_message("assistant", greeting_text(user)),
        _new_message(role, message_text),
    ]
    conversation_id = await session.scalar(
        _CREATE, {"user_id": user_id, "messages": messages}
    )
    return conversation_id, messages


async def append_message(
    session: AsyncSession, conversation_id: uuid.UUID, role: str, message_text: str
) -> dict | None:
    """Add one message. Returns it, or None if no live conversation matched."""
    message = {
        "role": role,
        "text": message_text,
        # Minted here, never taken from the caller: a client-supplied id can
        # collide with one already in the array, and a client clock skews order.
        "message_id": str(uuid.uuid4()),
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
    }
    # A one-element list, because || on two arrays appends elements; passing
    # the bare object would rely on Postgres' lone-object special case.
    found = await session.scalar(
        _APPEND, {"message": [message], "conversation_id": conversation_id}
    )
    # Zero rows means absent *or* soft-deleted. Without this the route would
    # report success on a conversation it never wrote to.
    return message if found is not None else None
