"""The embedded passages of a patient's record, for retrieval."""

from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base

__all__ = ["EMBEDDING_DIM", "RecordChunk"]

# The width of openai/text-embedding-3-small. Fixed by the column type: a
# different embedding model means a new migration and a full re-index.
EMBEDDING_DIM = 1536


class RecordChunk(Base):
    """One chunk from rag_pipeline.chunks, with its embedding.

    Written and read through langchain-postgres' PGVectorStore
    (rag_pipeline/vector_store.py), not the ORM. It is declared here anyway
    so the schema is owned by Alembic: a table missing from Base.metadata is
    one autogenerate offers to drop. The column names are the ones
    PGVectorStore expects by default.
    """

    __tablename__ = "record_chunks"

    # The chunk_id ("pat_...:allergy:01"), which is not a UUID -- the store's
    # default id type -- so the column is declared as text. Being the key,
    # re-indexing the same record replaces rows rather than duplicating them.
    langchain_id: Mapped[str] = mapped_column(Text, primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    # Real columns rather than keys in the JSON blob, so the per-patient
    # filter every search applies is an indexed WHERE.
    patient_id: Mapped[str] = mapped_column(Text, index=True)
    kind: Mapped[str] = mapped_column(Text)
    langchain_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)
