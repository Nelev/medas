"""ORM models.

Import every model here. Alembic's autogenerate only sees tables already
registered on ``Base.metadata``, so a model that is never imported is
silently invisible -- and autogenerate will emit a migration dropping its
table. Importing them here means ``import model`` is enough.
"""

from database.database import Base
from model.conversation import (
    Conversation,
    create_conversation,
    greeting_texts,
    list_conversations,
)
from model.message import Message, MessageRole, append_message, list_messages
from model.record_chunk import RecordChunk
from model.user import (
    User,
    UserRole,
    create_clerk_user,
    link_clerk_user,
    user_by_clerk_id,
)

__all__ = [
    "Base",
    "Conversation",
    "Message",
    "MessageRole",
    "RecordChunk",
    "User",
    "UserRole",
    "append_message",
    "create_clerk_user",
    "create_conversation",
    "greeting_texts",
    "link_clerk_user",
    "list_conversations",
    "list_messages",
    "user_by_clerk_id",
]
