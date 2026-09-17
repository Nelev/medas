"""add conversations table

Revision ID: 9c4d1f2a7b30
Revises: 6f1a2b3c4d5e
Create Date: 2026-09-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9c4d1f2a7b30"
down_revision: str | None = "6f1a2b3c4d5e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        # Defaulting to '[]' rather than NULL keeps the append total: NULL ||
        # anything is NULL, which would drop the first message of every
        # conversation without raising.
        sa.Column(
            "messages",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        # Maintained by append_message's own UPDATE rather than by
        # SQLAlchemy's onupdate, which raw SQL bypasses. Writes made outside
        # the app (psql, pgAdmin) still will not touch it; add a trigger here
        # if that matters.
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("conversation_id"),
    )
    op.create_index(op.f("ix_conversations_user_id"), "conversations", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_conversations_user_id"), table_name="conversations")
    op.drop_table("conversations")
