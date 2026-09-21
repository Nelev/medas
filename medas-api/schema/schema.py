"""Schemas for the message endpoints."""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["MessageRequest", "NewConversation", "NewMessage"]

# Long enough for anyone describing a symptom, short enough that a caller
# cannot turn one request into an unbounded prompt. Without a ceiling the
# body size is the only limit, and it is the model bill that pays for it.
MAX_TEXT_LENGTH = 4000


class MessageRequest(BaseModel):
    # str_strip_whitespace runs before the length check, so min_length=1 sees
    # the stripped value: a whitespace-only body is rejected at the edge with
    # a 422 rather than reaching the pipeline as an empty prompt. min_length
    # alone would not do this -- " " is one character and would pass.
    model_config = ConfigDict(str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)
    user_name: str = Field(min_length=1, max_length=200)


class NewMessage(BaseModel):
    """Body of a message being added to an existing conversation.

    No message_id and no timestamp: both are server-side (see append_message).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)


class NewConversation(NewMessage):
    """First message of a conversation that does not exist yet.

    Two identifiers, because the app currently has two: user_id is the FK that
    owns the row, `user` is the opaque patient id the UI greets by. They
    collapse into one -- read from the session, not the body -- once auth
    lands and the greeting can be resolved server-side.
    """

    user_id: uuid.UUID
    user: str = Field(min_length=1)
