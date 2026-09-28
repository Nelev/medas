"""The pgvector-backed index of the record, shared by ingest and search."""

import os
from functools import lru_cache

from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGEngine, PGVectorStore
from sqlalchemy.ext.asyncio import AsyncEngine

from model.record_chunk import RecordChunk
from utils import OPENROUTER_BASE_URL

__all__ = [
    "EMBEDDING_MODEL",
    "EMBEDDING_TIMEOUT_SECONDS",
    "get_embeddings",
    "get_vector_store",
    "init_vector_store",
]

# One model for both sides: vectors from different models live in different
# spaces, so a query embedded with anything else matches nothing reliably.
EMBEDDING_MODEL = "openai/text-embedding-3-small"

# An embedding is one short round trip; a request still running after this is
# hung, and it is in the path of every record search.
EMBEDDING_TIMEOUT_SECONDS = 20.0

_store: PGVectorStore | None = None


@lru_cache
def get_embeddings() -> OpenAIEmbeddings:
    """Built on first use, so importing this module needs no credentials."""
    return OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=os.getenv("OPENROUTER_API_KEY"),
        timeout=EMBEDDING_TIMEOUT_SECONDS,
        # Otherwise the client tokenizes locally with tiktoken and sends token
        # ids, which OpenRouter does not accept; send plain text.
        check_embedding_ctx_length=False,
    )


async def init_vector_store(engine: AsyncEngine) -> PGVectorStore:
    """Open the store over record_chunks, on the app's own engine.

    from_engine rather than from_connection_string: the latter opens a second
    pool, outside DbSettings' sizing and pre-ping and never disposed, and runs
    it on a background thread's loop, so every search would hop threads twice.
    Called once, awaited, from the lifespan (or the ingest script), so the
    table lookup it does never blocks a request. The table itself is created
    by Alembic, never here.
    """
    global _store
    _store = await PGVectorStore.create(
        engine=PGEngine.from_engine(engine),
        embedding_service=get_embeddings(),
        table_name=RecordChunk.__tablename__,
        metadata_columns=["patient_id", "kind"],
    )
    return _store


def get_vector_store() -> PGVectorStore:
    if _store is None:
        raise RuntimeError("init_vector_store() has not been called")
    return _store
