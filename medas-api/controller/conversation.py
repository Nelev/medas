"""Asking the agent within a conversation, and reading one back.

No HTTP here: a missing conversation or user is a NotFound, and the app
decides what status that is. The routes stay a thin mapping, and this is where
the flow -- what is read, what is written, and when it is committed -- lives.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from langchain_agent.agent import answer as ask_agent
from langchain_agent.patient import record_id
from model import MessageRole, append_message, create_conversation, list_messages
from schema import (
    AgentUnavailable,
    Attachment,
    ConversationNotFound,
    NewMessage,
    UserNotFound,
)
from utils import messages_as_turns, parse_agent_reply

UNAVAILABLE_REPLY = "Sorry, I couldn't answer that just now. Please try again."

__all__ = [
    "answer_and_store",
    "ask_question",
    "get_conversation",
    "write_user_turn",
]


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
    # Read before the new turn is written, so the model is not shown the
    # question it is being asked twice.
    history = (
        await get_conversation(session, user_id, conversation_id)
        if conversation_id is not None
        else None
    )

    conversation_id, written = await write_user_turn(
        session, user_id, name, message.role, message.text, conversation_id
    )

    if history is None:
        # The greeting, then the question: everything before the question is
        # what the patient has seen.
        history = written[:-1]

    reply = await answer_and_store(
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


async def write_user_turn(
    session: AsyncSession,
    user_id: uuid.UUID,
    name: str | None,
    role: str,
    text: str,
    conversation_id: uuid.UUID | None,
) -> tuple[uuid.UUID, list[dict]]:
    """Write a user turn, starting a conversation for it when there is none,
    and commit it.

    Returns the conversation's id and what was written: the greeting and the
    turn on a new conversation, the turn alone on an existing one.
    """
    if conversation_id is None:
        try:
            conversation_id, written = await create_conversation(
                session, user_id, name, role, text
            )
        except IntegrityError as exc:
            # The only constraint here is the user_id FK. current_user has
            # just found the row, so this is a user deleted since.
            raise UserNotFound from exc
    else:
        sent = await append_message(
            session, conversation_id, role, text, user_id=user_id
        )
        if sent is None:
            # Live a moment ago and not now. The write is the only authority.
            raise ConversationNotFound

        written = [sent]

    # Committed before the model call, so a run of several round trips does
    # not hold a write transaction open for its duration.
    await session.commit()

    return conversation_id, written


async def answer_and_store(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    turns: list[dict],
    attachments: Sequence[Attachment] = (),
) -> dict:
    """Ask the agent, and store what it answers. Not committed.

    `attachments` are PDFs sent with the last turn, for the document tool.
    """
    # The record searched is the signed-in user's, by the pat_{users.id}
    # convention langchain_agent/patient.py owns.
    try:
        reply = await ask_agent(
            turns, record_id=record_id(user_id), attachments=attachments
        )
    except AgentUnavailable:
        # The question is already committed, so leave an answer beside it
        # rather than a thread that ends on an unanswered turn.
        await append_message(
            session,
            conversation_id,
            MessageRole.ASSISTANT,
            UNAVAILABLE_REPLY,
            user_id=user_id,
        )
        await session.commit()
        raise
    reply_text, extra = parse_agent_reply(reply)

    return await append_message(
        session,
        conversation_id,
        MessageRole.ASSISTANT,
        reply_text,
        extra=extra,
        user_id=user_id,
    )
