"""What a run carries besides its messages, for the tools to read."""

import uuid
from typing import NotRequired

from langchain.agents import AgentState

from schema import Attachment


class RecordState(AgentState):
    """The agent's state: the thread, and the run's own data.

    The caller sets `record_id` and `attachments` in the input and the tools
    read them from `runtime.state`, which LangChain injects and leaves out of
    the tools' schemas: the model names a document, it cannot choose whose
    record is read or supply a file.
    """

    record_id: str
    # Whose conversation this is, for the tool that reads it back: the ids the
    # server holds, so the model cannot export anyone else's.
    user_id: NotRequired[uuid.UUID]
    conversation_id: NotRequired[uuid.UUID]
    # The PDFs sent with this question, the only ones the document tools can
    # reach.
    attachments: NotRequired[tuple[Attachment, ...]]
