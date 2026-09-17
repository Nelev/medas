"""ORM models.

Import every model here. Alembic's autogenerate only sees tables already
registered on ``Base.metadata``, so a model that is never imported is
silently invisible -- and autogenerate will emit a migration dropping its
table. Importing them here means ``import model`` is enough.
"""

from database.database import Base
from model.conversation import (
    Conversation,
    append_message,
    create_conversation,
    greeting_text,
)
from model.user import User, UserRole

__all__ = [
    "Base",
    "Conversation",
    "User",
    "UserRole",
    "append_message",
    "create_conversation",
    "greeting_text",
]
