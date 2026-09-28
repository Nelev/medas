"""Asking the agent within a conversation, and reading one back.

No HTTP here: a missing conversation or user is a NotFound, and the app
decides what status that is. The routes stay a thin mapping, and this is where
the flow -- what is read, what is written, and when it is committed -- lives.
"""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agent.patient import record_id
from langchain_agent.agent import answer as ask_agent
from model import MessageRole, append_message, create_conversation, list_messages
from schema import NewMessage
from utils import messages_as_turns, parse_agent_reply

__all__ = [
    "ConversationNotFound",
    "NotFound",
    "UserNotFound",
    "ask_question",
    "get_conversation",
]


class NotFound(Exception):
    """Something the caller asked for is not there; `detail` says what."""

    detail = "Not found"


class ConversationNotFound(NotFound):
    """Unknown, soft-deleted or someone else's: one answer for all three, so
    an id cannot be probed for."""

    detail = "Conversation not found"


class UserNotFound(NotFound):
    """The signed-in user's row is gone: deleted since current_user found it."""

    detail = "User not found"


async def ask_question(
    session: AsyncSession,
    user_id: uuid.UUID,
    name: str | None,
    message: NewMessage,
    conversation_id: uuid.UUID | None,
) -> tuple[uuid.UUID, list[dict]]:
    """Ask the agent. Starts a conversation when there is not one yet.

    Returns the conversation's id and the turns this call added: on a new
    conversation the greeting, the question and the answer; on a later one
    the question and the answer. The client appends them to what it has.

    One flow for every question, because the only difference between the
    first and the rest is whether a thread exists to hang it on -- and a
    caller that has just opened the app should not have to know that.

    Memory comes from the messages table rather than a LangGraph checkpointer.
    One store of a conversation, not two: a checkpointer would keep its own
    copy of the thread, and the copy the UI renders is this one.

    `name` is the one the greeting addresses, read only when a conversation
    is started.
    """
    if conversation_id is None:
        try:
            conversation_id, written = await create_conversation(
                session, user_id, name, message.role, message.text
            )
        except IntegrityError as exc:
            # The only constraint here is the user_id FK. current_user has
            # just found the row, so this is a user deleted since.
            raise UserNotFound from exc

        # The greeting, then the question: everything before the question is
        # what the patient has seen.
        history = written[:-1]
    else:
        # Read before the new turn is written, so the model is not shown the
        # question it is being asked twice.
        history = await get_conversation(session, user_id, conversation_id)

        sent = await append_message(
            session, conversation_id, message.role, message.text, user_id=user_id
        )
        if sent is None:
            # Live a moment ago and not now. The write is the only authority.
            raise ConversationNotFound

        written = [sent]

    # Committed before the model call, so a run of several round trips does
    # not hold a write transaction open for its duration.
    await session.commit()

    reply = await _answer_and_store(
        session,
        conversation_id,
        user_id,
        messages_as_turns(history, message.text),
    )
    await session.commit()

    return conversation_id, [*written, reply]


async def get_conversation(
    session: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID
) -> list[dict]:
    """Every message in one of user_id's conversations, oldest first."""
    messages = await list_messages(session, conversation_id, user_id=user_id)

    # A live conversation always holds at least the greeting it was seeded
    # with, so nothing back means unknown, soft-deleted or someone else's.
    if not messages:
        raise ConversationNotFound

    return messages


async def _answer_and_store(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    turns: list[dict],
) -> dict:
    """Ask the agent, and store what it answers."""
    # The record searched is the signed-in user's, by the pat_{users.id}
    # convention agent/patient.py owns.
    reply = await ask_agent(turns, record_id=record_id(user_id))
    reply_text, extra = parse_agent_reply(reply)

    return await append_message(
        session,
        conversation_id,
        MessageRole.ASSISTANT,
        reply_text,
        extra=extra,
        user_id=user_id,
    )
