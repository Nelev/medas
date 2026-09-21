"""Messages: one row each, and the two statements that touch them.

A conversation's history used to be a jsonb array on the conversation row,
appended to with ``messages = messages || :message``. That is correct but
O(N): Postgres has no in-place update, so appending the tenth message
rewrites the nine before it, and every writer on that conversation queues
behind the rewrite. Here each message is its own row, so an append is an
INSERT that touches nothing else and blocks nobody.
"""

import datetime
import enum
import json
import uuid
from collections.abc import Sequence

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Row,
    Text,
    Uuid,
    bindparam,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base

__all__ = [
    "Message",
    "MessageRole",
    "add_messages",
    "append_message",
    "list_messages",
]


class MessageRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class Message(Base):
    __tablename__ = "messages"

    # Ordering is by seq, so that is the index conversations are read through.
    # Unique as well as ordered: seq comes from a sequence, and a duplicate
    # would mean two messages with no defined order between them.
    __table_args__ = (
        Index(
            "ix_messages_conversation_id_seq",
            "conversation_id",
            "seq",
            unique=True,
        ),
    )

    # The uuid stays the primary key because it is the id the client already
    # knows -- the UI reads `message_id` off every stored message. seq below
    # orders; this identifies.
    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.conversation_id", ondelete="CASCADE")
    )

    # A counter rather than a timestamp, even though created_at below is
    # distinct per row: a counter cannot run backwards when the clock is
    # stepped, and it is a stable pagination cursor -- "everything after seq
    # N" stays correct where "everything after instant T" can skip a row
    # written a microsecond earlier by a slower transaction.
    #
    # Assigned globally, not per conversation. Order within a conversation is
    # insert order, which a global sequence preserves exactly, and the gaps
    # left by other conversations mean nothing. Numbering per conversation
    # would need MAX(seq) + 1, and that needs either a lock on the
    # conversation row -- putting back the serialisation this table removes --
    # or a retry loop on the unique violation.
    #
    # BY DEFAULT rather than ALWAYS, so the migration that backfilled this
    # table could supply its own values.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=False))

    role: Mapped[MessageRole] = mapped_column(
        # values_callable stores the member values ("user"), not the names
        # ("USER") -- the same treatment users.role gets.
        Enum(
            MessageRole,
            name="message_role",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        )
    )

    content: Mapped[str] = mapped_column(Text)

    # Whatever the writer knew and a later reader may want: for an assistant
    # turn, the severity and confidence it assigned. Named `meta` on the class
    # because `metadata` is SQLAlchemy's own attribute on Base.
    meta: Mapped[dict] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb")
    )

    # clock_timestamp(), not now(): now() is the transaction's start time, so
    # messages written together would all carry the same instant. Messages are
    # immutable, so there is no updated_at.
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )


# One statement for every write, however many messages it carries.
#
# The conversation has to exist and not be soft-deleted, and making that the
# SELECT's WHERE clause checks it in the same statement that writes -- a
# SELECT first would leave a window between the check and the write. No rows
# selected means no rows inserted and nothing returned, which is how the
# caller learns it matched nothing. (When the caller is an authenticated user
# rather than a query parameter, `AND c.user_id = :user_id` joins this one
# WHERE clause and every write path is covered at once.)
#
# Parallel arrays rather than a VALUES list, so the statement is fixed text
# for any number of messages -- built once, at import, and reused. ORDER BY
# r.ord is what makes seq assignment follow the caller's order rather than
# whatever order the planner emits rows in.
#
# The RETURNING of an INSERT has no defined row order, so it is wrapped in a
# CTE and ordered by seq on the way out.
_WRITE = text(
    "WITH m AS ("
    "INSERT INTO messages (conversation_id, role, content, metadata) "
    "SELECT c.conversation_id, r.role::message_role, r.content, r.meta::jsonb "
    "FROM conversations c "
    "CROSS JOIN unnest(:roles, :contents, :metas) "
    "WITH ORDINALITY AS r(role, content, meta, ord) "
    "WHERE c.conversation_id = :conversation_id AND NOT c.deleted "
    "ORDER BY r.ord "
    "RETURNING message_id, seq, role, content, metadata, created_at"
    ") "
    "SELECT m.message_id, m.role, m.content, m.metadata AS meta, m.created_at "
    "FROM m ORDER BY m.seq"
).bindparams(
    bindparam("roles", type_=ARRAY(Text)),
    bindparam("contents", type_=ARRAY(Text)),
    # Text, not JSONB: asyncpg encodes a jsonb[] inconsistently across
    # versions, and casting each element in SQL is one character of work.
    bindparam("metas", type_=ARRAY(Text)),
)


# The join is the soft-delete check: a deleted conversation's messages are
# still rows, and reading them back would be reading a deleted thread.
_LIST = text(
    "SELECT m.message_id, m.role, m.content, m.metadata AS meta, m.created_at "
    "FROM messages m "
    "JOIN conversations c ON c.conversation_id = m.conversation_id "
    "WHERE m.conversation_id = :conversation_id AND NOT c.deleted "
    "ORDER BY m.seq"
)


def _wire(row: Row) -> dict:
    """One stored row as the API sends it.

    Columns are named for the database -- content, created_at, metadata --
    and the wire has called them text, timestamp and top-level fields since
    before this table existed. This is the single place the two meet, so the
    storage change does not reach the UI.

    Metadata is spread underneath the minted fields, matching how it was
    merged when it lived in the array: nothing stored can shadow the role,
    the text, the id or the timestamp.

    Both _WRITE and _LIST project these five names, and must keep doing so:
    a column renamed in one of them surfaces here as an AttributeError on
    the first request, not at import. Spelled out in each statement rather
    than shared through an interpolated constant, which is string-built SQL
    however harmless the string -- and worth keeping the linter loud about
    in a module that is nothing but hand-written statements.
    """
    return {
        **(row.meta or {}),
        "role": row.role,
        "text": row.content,
        "message_id": str(row.message_id),
        "timestamp": row.created_at.isoformat(),
    }


async def add_messages(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    messages: Sequence[tuple[str, str, dict | None]],
) -> list[dict]:
    """Write messages to a live conversation, in order, as they are given.

    Returns them as stored -- read back from the database rather than echoed,
    because message_id and created_at are the database's to mint. Empty if
    the conversation is unknown or soft-deleted, which is the one signal
    every caller needs and the only one the statement can give.
    """
    result = await session.execute(
        _WRITE,
        {
            "conversation_id": conversation_id,
            "roles": [role for role, _, _ in messages],
            "contents": [content for _, content, _ in messages],
            "metas": [json.dumps(meta or {}) for _, _, meta in messages],
        },
    )
    return [_wire(row) for row in result]


async def append_message(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    role: str,
    message_text: str,
    extra: dict | None = None,
) -> dict | None:
    """Add one message. Returns it, or None if no live conversation matched.

    `extra` carries whatever the writer knows and a later reader may want --
    for an assistant turn, the severity it assigned. It is stored as the
    message's metadata rather than flattened into it, so a field added there
    later cannot collide with a column.
    """
    written = await add_messages(
        session, conversation_id, [(role, message_text, extra)]
    )
    # Nothing written means the conversation is absent or soft-deleted.
    # Without this the route would report success on a write that never
    # happened.
    return written[0] if written else None


async def list_messages(
    session: AsyncSession, conversation_id: uuid.UUID
) -> list[dict]:
    """Every message in a conversation, oldest first.

    Empty for a conversation that is unknown or soft-deleted -- and only for
    those, since a live conversation always holds at least the greeting it
    was seeded with.
    """
    result = await session.execute(_LIST, {"conversation_id": conversation_id})
    return [_wire(row) for row in result]
