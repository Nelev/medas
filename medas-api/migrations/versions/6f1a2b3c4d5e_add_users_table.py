"""add users table

Revision ID: 6f1a2b3c4d5e
Revises:
Create Date: 2026-09-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6f1a2b3c4d5e"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column(
            "role",
            sa.Enum("user", "admin", name="user_role"),
            server_default="user",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # updated_at is maintained by SQLAlchemy's onupdate, so writes made
        # outside the app (psql, pgAdmin) will not touch it. Add a trigger here
        # if that matters.
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )


def downgrade() -> None:
    op.drop_table("users")
    # drop_table leaves the enum type behind; remove it explicitly.
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=False)
