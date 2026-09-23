"""add clerk_user_id to users

Revision ID: d8e2f4a6b1c3
Revises: c3a5e1d97b24
Create Date: 2026-09-23

Who a request is from now comes from a verified Clerk session token, whose
subject is Clerk's id for the person ("user_2abc..."), not ours. This column
joins the two. Nullable, because a row exists before anyone has signed in as
it: it is filled in on that first sign-in, by matching the account's verified
email (see auth/session.py). Unique, so one Clerk account can only ever be one
user -- the unique constraint is also the index the per-request lookup uses.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d8e2f4a6b1c3"
down_revision: str | None = "c3a5e1d97b24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("clerk_user_id", sa.String(length=64), nullable=True)
    )
    op.create_unique_constraint("uq_users_clerk_user_id", "users", ["clerk_user_id"])


def downgrade() -> None:
    op.drop_constraint("uq_users_clerk_user_id", "users", type_="unique")
    op.drop_column("users", "clerk_user_id")
