"""Retrieval over one patient's record, for the context block.

Called when the model asks for it rather than before: it decides what is
worth looking up, and in its own wording.
"""

from typing import Any

from rag_pipeline.vector_store import get_vector_store

__all__ = ["search_record"]


async def search_record(
    query: str, patient_id: str, n_results: int = 5
) -> list[dict[str, Any]]:
    """The passages of this patient's record nearest to `query`.

    patient_id is a filter, not a hint: it comes from the caller, so a question
    cannot reach another patient's record however it is phrased. It is applied
    in the SQL, on an indexed column, not to the results afterwards.

    The distance is returned along with the text because it is the only signal
    of whether anything relevant was found -- the store gives back the nearest
    passages whether or not any of them are near.
    """
    # Embeds the query with the corpus's model, then runs the search, both
    # awaited so neither blocks the event loop behind it.
    results = await get_vector_store().asimilarity_search_with_score(
        query, k=n_results, filter={"patient_id": patient_id}
    )
    return [
        {"chunk_id": doc.id, "text": doc.page_content, "distance": float(distance)}
        for doc, distance in results
    ]
