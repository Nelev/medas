"""Schemas for the message endpoints."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["NewMessage"]

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
