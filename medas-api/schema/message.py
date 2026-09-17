"""Schemas for the message endpoints."""

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["MessageRequest"]


class MessageRequest(BaseModel):
    # str_strip_whitespace runs before the length check, so min_length=1 sees
    # the stripped value: a whitespace-only body is rejected at the edge with
    # a 422 rather than reaching the pipeline as an empty prompt. min_length
    # alone would not do this -- " " is one character and would pass.
    model_config = ConfigDict(str_strip_whitespace=True)

    message: str = Field(min_length=1)
    user_name: str = Field(min_length=1)
