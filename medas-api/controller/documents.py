"""Adding a PDF the user uploads to their record, through the agent.

An upload is a turn in the conversation, the way a question is: a user turn
records the request, the chat agent is asked to add the file (its document
tools check it -- load_pdf, then the model check in rag_pipeline/verify.py --
and store it), and its reply, stored or refused, is the assistant turn.
"""

import uuid

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from controller.conversation import NotFound, answer_and_store, write_user_turn
from langchain_agent.documents import Attachment
from langchain_agent.patient import record_id
from model import MessageRole
from rag_pipeline.record import find_record
from utils import messages_as_turns

__all__ = ["RecordNotFound", "index_upload"]

# The user's turn an upload writes, before the agent is asked.
UPLOAD_REQUESTED = "upload file requested"


class RecordNotFound(NotFound):
    """The signed-in user has no medical record to add a document to."""

    detail = "Record not found"


async def index_upload(
    session: AsyncSession,
    user_id: uuid.UUID,
    greeting_name: str | None,
    file: UploadFile,
    conversation_id: uuid.UUID | None,
) -> tuple[uuid.UUID, list[dict]]:
    """Have the agent verify and store `file`, as turns in a conversation.

    Like ask_question: starts a conversation when there is not one yet, and
    returns its id and the turns this call added -- the upload request and
    the agent's answer, stored or refused.
    """
    # Checked here as well as in the tools, so a user without a record costs
    # no model call.
    if find_record(record_id(user_id)) is None:
        raise RecordNotFound

    conversation_id, written = await write_user_turn(
        session,
        user_id,
        greeting_name,
        MessageRole.USER,
        UPLOAD_REQUESTED,
        conversation_id,
    )

    # Without the conversation's history: the agent is checking a file, and
    # what was said before has no bearing on whether it belongs.
    name = file.filename or "upload.pdf"
    answered = await answer_and_store(
        session,
        conversation_id,
        user_id,
        messages_as_turns([], f"Please add the attached document {name} to my record."),
        attachments=[Attachment(name, await file.read())],
    )
    await session.commit()

    return conversation_id, [*written, answered]
