"""Adding a PDF the user uploads to their record, through the agent.

The agent is the one the chat uses, asked to add the file: its document tools
check it (load_pdf, then the model check in rag_pipeline/verify.py) and store
it. Whether it was stored is read from what the store tool did, not from what
the model says; its reply is passed back as the message.
"""

import uuid

from fastapi import UploadFile

from controller.conversation import NotFound
from langchain_agent.agent import answer
from langchain_agent.documents import Attachment
from langchain_agent.patient import record_id
from rag_pipeline.pdf import Rejected
from rag_pipeline.record import find_record
from utils import messages_as_turns, parse_agent_reply

__all__ = ["DocumentNotStored", "RecordNotFound", "index_upload"]


class RecordNotFound(NotFound):
    """The signed-in user has no medical record to add a document to."""

    detail = "Record not found"


class DocumentNotStored(Rejected):
    """The agent did not store the upload: a check refused it, or the run
    ended before it got that far. The message is the agent's."""


async def index_upload(user_id: uuid.UUID, file: UploadFile) -> dict:
    """Have the agent verify and store `file`. Returns the chunks it wrote and
    its message.

    Raises DocumentNotStored, with the agent's message, when the file was
    not stored.
    """
    # Checked here as well as in the tools, so a user without a record costs
    # no model call.
    record = find_record(record_id(user_id))
    if record is None:
        raise RecordNotFound

    name = file.filename or "upload.pdf"
    attachment = Attachment(name, await file.read())
    reply, stored = await answer(
        messages_as_turns([], f"Please add the attached document {name} to my record."),
        record_id=record["id"],
        attachments=[attachment],
    )
    message, _ = parse_agent_reply(reply)

    if name not in stored:
        raise DocumentNotStored(message)
    return {"chunks": stored[name], "message": message}
