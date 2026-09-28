"""add record_chunks table

Revision ID: 6804b584e3cc
Revises: d8e2f4a6b1c3
Create Date: 2026-09-28

The retrieval index moves from a local Chroma collection into Postgres, so the
record's embeddings live next to the rest of the data and survive as one
database. One row per chunk from rag_pipeline.chunks, read and written by
langchain-postgres' PGVectorStore (see model/record_chunk.py for why the
columns are named as they are).

The extension is created here rather than by the store at runtime, so the app
never needs the privilege to create one. It is left in place on downgrade:
dropping it would take with it anything else that came to depend on it.
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op

revision: str = "6804b584e3cc"
down_revision: str | None = "d8e2f4a6b1c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "record_chunks",
        sa.Column("langchain_id", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.VECTOR(dim=1536), nullable=False),
        sa.Column("patient_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("langchain_metadata", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("langchain_id"),
    )
    op.create_index(
        op.f("ix_record_chunks_patient_id"), "record_chunks", ["patient_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_record_chunks_patient_id"), table_name="record_chunks")
    op.drop_table("record_chunks")
