"""Index the medical record into pgvector: uv run python -m langchain_agent.rag"""

import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.documents import Document

from database.database import dispose_engine, init_engine
from rag_pipeline.chunks import iter_chunks
from rag_pipeline.pdf import aindex_pdfs
from rag_pipeline.vector_store import init_vector_store

MEDICAL_HISTORY_PATH = (
    Path(__file__).parent.parent / "rag_pipeline" / "medical_history.json"
)
# The seeded patient's PDFs. Synthetic for now; see dataset/README.md.
DOCUMENTS_PATH = Path(__file__).parent.parent / "dataset" / "documents"


def load_record() -> dict:
    with MEDICAL_HISTORY_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def load_documents(record: dict) -> list[Document]:
    """One Document per clinical record from rag_pipeline.chunks. The chunk id
    is the document id, which the store keys rows on, so re-indexing replaces
    rows rather than adding to them."""
    return [
        Document(
            id=chunk["chunk_id"],
            page_content=chunk["text"],
            metadata={"kind": chunk["kind"], **chunk["metadata"]},
        )
        for chunk in iter_chunks(record)
    ]


async def run():
    # Kept in a function: add_documents and similarity_search make billable
    # embedding calls, so importing this module must not fire them.
    vector_store = await init_vector_store(init_engine())
    try:
        record = load_record()
        docs = load_documents(record)
        await vector_store.aadd_documents(docs)
        pdf_chunks = await aindex_pdfs(sorted(DOCUMENTS_PATH.glob("*.pdf")), record)
        print(f"Indexed {len(docs)} record chunks and {pdf_chunks} PDF chunks")

        question = "Do I have any allergies?"
        print(f"\nQ: {question}")
        results = await vector_store.asimilarity_search_with_score(question, k=3)
        for doc, distance in results:
            print(f"\n[{distance:.3f}] {doc.id}: {doc.page_content}")
    finally:
        await dispose_engine()


if __name__ == "__main__":
    # The key is read from the environment; main.py does this for the app.
    load_dotenv()
    asyncio.run(run())
