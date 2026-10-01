"""Schemas for the message endpoints."""

from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "Attachment",
    "Chunk",
    "ConversationNotFound",
    "NewMessage",
    "NotFound",
    "RecordContext",
    "RecordNotFound",
    "Rejected",
    "UserNotFound",
]

# Long enough for anyone describing a symptom, short enough that a caller
# cannot turn one request into an unbounded prompt. Without a ceiling the
# body size is the only limit, and it is the model bill that pays for it.
MAX_TEXT_LENGTH = 4000


class NewMessage(BaseModel):
    """Body of POST /ask: the message being asked, new conversation or not.

    No message_id and no timestamp: both are server-side (see append_message).
    """

    # str_strip_whitespace runs before the length check, so min_length=1 sees
    # the stripped value: a whitespace-only body is rejected at the edge with
    # a 422 rather than reaching the pipeline as an empty prompt. min_length
    # alone would not do this -- " " is one character and would pass.
    model_config = ConfigDict(str_strip_whitespace=True)

    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)


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


class RecordNotFound(NotFound):
    """The signed-in user has no medical record to add a document to."""

    detail = "Record not found"


class Rejected(Exception):
    """The document is not indexed; the message says why."""


class Chunk(TypedDict):
    """One embeddable unit: the text, plus what you need to filter and cite."""

    chunk_id: str
    kind: str
    text: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class Attachment:
    """A PDF sent with the question. `name` is what the model calls it by."""

    name: str
    content: bytes


@dataclass(frozen=True)
class RecordContext:
    """Per-run data for the tools, passed at invoke time, never by the model."""

    record_id: str
    # The PDFs sent with this question, the only ones the document tools can
    # reach: the model names one, it cannot supply one.
    attachments: tuple[Attachment, ...] = ()
