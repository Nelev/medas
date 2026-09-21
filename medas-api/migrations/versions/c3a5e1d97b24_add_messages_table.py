"""move conversation messages into their own table

Revision ID: c3a5e1d97b24
Revises: 9c4d1f2a7b30
Create Date: 2026-09-21

Messages lived in a jsonb array on the conversation row. Appending to it
rewrote the whole row, so the cost of adding a message grew with the length
of the conversation and every writer on that conversation queued behind the
rewrite. One row per message costs a join and buys constant-time appends,
ordering, and a typed role.

The data moves with it: message ids and timestamps already stored are kept
as they are, so nothing that was written before this runs changes identity.
Both directions are implemented -- downgrade rebuilds the arrays from the
rows.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3a5e1d97b24"
down_revision: str | None = "9c4d1f2a7b30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# seq is the element's position in its own array, not a global row number:
# the unique index is (conversation_id, seq), so numbering only has to
# increase *within* a conversation. Numbering globally would mean sorting
# every message in the database to assign it, and buy nothing.
#
# `e - 'key'` drops a key from the jsonb object, so what is left is whatever
# the writer stored beyond the four fields that became columns -- severity
# and confidence on an assistant turn.
_BACKFILL_MESSAGES = """
INSERT INTO messages
    (message_id, conversation_id, seq, role, content, metadata, created_at)
SELECT COALESCE((e->>'message_id')::uuid, gen_random_uuid()),
       c.conversation_id,
       t.ord,
       (e->>'role')::message_role,
       COALESCE(e->>'text', ''),
       e - 'message_id' - 'role' - 'text' - 'timestamp',
       COALESCE((e->>'timestamp')::timestamptz, now())
FROM conversations c
CROSS JOIN LATERAL jsonb_array_elements(c.messages)
     WITH ORDINALITY AS t(e, ord)
"""

# Those explicit seq values bypassed the identity sequence, which is still
# sitting at 1. Left alone, the first message written after this migration
# would collide with a backfilled one. Setting it past the longest
# conversation is enough: every later append then lands after everything
# already in its own conversation.
_RESET_SEQ = """
SELECT setval(pg_get_serial_sequence('messages', 'seq'),
              COALESCE((SELECT MAX(seq) FROM messages), 0) + 1,
              false)
"""

# The column held the last append's time, because an append rewrote this row.
# Nothing writes it now, so it is renamed to what it will hold from here --
# and corrected to it, from the greeting the conversation was seeded with.
# Read out of the array still sitting on the row, rather than out of the
# messages just inserted: same answer, one pass, no aggregate.
_RESET_CREATED_AT = """
UPDATE conversations
SET created_at = COALESCE((messages->0->>'timestamp')::timestamptz, created_at)
"""

# The inverse: metadata underneath the four minted fields, so a stored key
# cannot shadow one of them -- the precedence the application always used.
_REBUILD_ARRAYS = """
UPDATE conversations c
SET messages = COALESCE((
    SELECT jsonb_agg(
               m.metadata || jsonb_build_object(
                   'role', m.role,
                   'text', m.content,
                   'message_id', m.message_id,
                   'timestamp', to_jsonb(m.created_at)
               )
               ORDER BY m.seq
           )
    FROM messages m
    WHERE m.conversation_id = c.conversation_id
), '[]'::jsonb)
"""


def upgrade() -> None:
    op.create_table(
        "messages",
        sa.Column(
            "message_id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        # BY DEFAULT rather than ALWAYS, because the backfill below supplies
        # its own values -- GENERATED ALWAYS would reject them without an
        # explicit OVERRIDING clause.
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "role",
            sa.Enum("user", "assistant", name="message_role"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.conversation_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("message_id"),
    )
    op.create_index(
        "ix_messages_conversation_id_seq",
        "messages",
        ["conversation_id", "seq"],
        unique=True,
    )

    op.execute(_BACKFILL_MESSAGES)
    op.execute(_RESET_SEQ)

    op.alter_column("conversations", "updated_at", new_column_name="created_at")
    op.execute(_RESET_CREATED_AT)

    # Last, so everything above still had the array to read.
    op.drop_column("conversations", "messages")


def downgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "messages",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.execute(_REBUILD_ARRAYS)

    # Back to the old name. The value stays the conversation's creation
    # instant rather than its last append -- the append times are in the
    # rebuilt array, and re-deriving them here would be inventing precision
    # the column never had a writer for.
    op.alter_column("conversations", "created_at", new_column_name="updated_at")

    op.drop_index("ix_messages_conversation_id_seq", table_name="messages")
    op.drop_table("messages")
    # Dropped by hand: create_table created the type implicitly, but
    # drop_table does not remove it, and a later upgrade would then fail with
    # "type message_role already exists".
    sa.Enum(name="message_role").drop(op.get_bind())
