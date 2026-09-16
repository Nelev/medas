"""Schemas for the message endpoints."""

from pydantic import BaseModel, Field

__all__ = ["MessageRequest"]


class MessageRequest(BaseModel):
    # min_length=1 so a whitespace-only body is rejected at the edge with a
    # 422 rather than reaching the pipeline as an empty prompt.
    message: str = Field(min_length=1)
    user_name: str = Field(min_length=1)
