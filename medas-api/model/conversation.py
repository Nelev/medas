"""The conversation model, and starting one."""

import datetime
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Uuid, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base
from model.message import MessageRole, add_messages

__all__ = [
    "Conversation",
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
    deleted: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))

    # The row's one timestamp. It was `updated_at`, back when an append
    # rewrote this row and so genuinely updated it; adding a message now
    # writes only to `messages`, and bumping a column here would mean taking a
    # lock on this row -- the contention that moving messages out was meant to
    # remove. So the column holds what it always actually held for a
    # conversation, and is now named for it. Last activity is
    # MAX(messages.created_at).
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


_CREATE = text(
    "INSERT INTO conversations (user_id) VALUES (:user_id) RETURNING conversation_id"
)


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

    Two statements, because the messages reference a conversation that does
    not exist yet. Folding both into one data-modifying CTE would work -- the
    foreign key is checked after the statement, by which point the parent row
    is there -- but correctness would then rest on when Postgres fires its
    referential triggers, which is not something a reader should have to
    verify. The cost is one round trip per conversation created, next to the
    model calls the same request makes.

    Raises IntegrityError if user_id is not a real user -- the FK is the
    check.

    The greeting is built here rather than accepted from the caller:
    assistant turns are the server's to write, or a client could put words in
    its mouth.
    """
    conversation_id = await session.scalar(_CREATE, {"user_id": user_id})
    messages = await add_messages(
        session,
        conversation_id,
        [
            (MessageRole.ASSISTANT, greeting_text(user), None),
            (role, message_text, None),
        ],
    )
    return conversation_id, messages
