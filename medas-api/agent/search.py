"""Retrieval over one patient's record, for the context block.

Called when the model asks for it rather than before: it decides what is
worth looking up, and in its own wording.
"""

import asyncio
from functools import lru_cache
from pathlib import Path
from typing import Any

import chromadb

from rag_pipeline.embeddings import get_embedding_async

__all__ = ["search_record"]

CHROMA_PATH = Path(__file__).resolve().parent.parent / "rag_pipeline" / "chroma"
COLLECTION_NAME = "masm_medical_history"


@lru_cache
def _collection():
    """The collection, opened once: building the client is not cheap."""
    return chromadb.PersistentClient(path=str(CHROMA_PATH)).get_collection(
        COLLECTION_NAME
    )


async def search_record(
    query: str, patient_id: str, n_results: int = 5
) -> list[dict[str, Any]]:
    """The passages of this patient's record nearest to `query`.

    patient_id is a filter, not a hint: it comes from the caller, so a question
    cannot reach another patient's record however it is phrased.

    The distance is returned along with the text because it is the only signal
    of whether anything relevant was found -- the store gives back the nearest
    passages whether or not any of them are near.
    """
    # A network call, so it is awaited rather than blocking the event loop
    # behind it.
    embedding = await get_embedding_async(query)

    # The query itself cannot be: chromadb's PersistentClient is embedded and
    # synchronous, with no async counterpart -- AsyncHttpClient is for the
    # client/server mode. It is a local HNSW search, but a thread keeps even
    # that off the loop.
    result = await asyncio.to_thread(
        _collection().query,
        # query_embeddings, not query_texts: the latter would embed the
        # question with Chroma's own MiniLM instead of the model the corpus was
        # embedded with, and the two spaces are not comparable.
        query_embeddings=[embedding],
        where={"patient_id": patient_id},
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )

    return [
        {"chunk_id": chunk_id, "text": document, "distance": float(distance)}
        for chunk_id, document, distance in zip(
            result["ids"][0],
            result["documents"][0],
            result["distances"][0],
            strict=True,
        )
    ]
