"""Which medical record belongs to a user.

The record's id is "pat_" followed by the user's uuid. That is a convention
rather than a foreign key, so it lives in one place: here.
"""

import uuid

__all__ = ["record_id"]


def record_id(user_id: uuid.UUID | str) -> str:
    """The record id belonging to a user."""
    return f"pat_{user_id}"
