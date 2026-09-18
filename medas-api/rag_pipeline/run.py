import json
from pathlib import Path

import chromadb

from rag_pipeline.chunks import iter_chunks
from rag_pipeline.embeddings import get_embedding, get_embeddings_batch

MEDICAL_HISTORY_PATH = Path(__file__).parent / "medical_history.json"
CHROMA_PATH = Path(__file__).parent / "chroma"

with MEDICAL_HISTORY_PATH.open(encoding="utf-8") as f:
    document = json.load(f)


def run():
    # Kept in a function rather than at module level: the embedding calls
    # below are billable, so importing this module must not fire them.
    chunks = list(iter_chunks(document))
    print("Chunks generated:", len(chunks))
    embeddings = get_embeddings_batch([chunk["text"] for chunk in chunks])
    print("Embeddings generated:", len(embeddings), "vectors, dim", len(embeddings[0]))

    chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    collection = chroma_client.get_or_create_collection(
        name="masm_medical_history",
        # Fixed when the collection is first created and immutable after:
        # an existing collection keeps its own metric and ignores this.
        metadata={"hnsw:space": "cosine"},
    )
    # upsert, not add: re-running with an id that already exists makes add
    # keep the stored copy and silently discard the new one.
    collection.upsert(
        ids=[chunk["chunk_id"] for chunk in chunks],
        embeddings=embeddings,
        # Without these the query returns bare ids and distances, leaving
        # nothing to hand a model as context.
        documents=[chunk["text"] for chunk in chunks],
        metadatas=[chunk["metadata"] for chunk in chunks],
    )

    question = "What is the last patient episode?"
    result = collection.query(
        # query_embeddings, not query_texts: the latter would embed the
        # question with Chroma's own 384-dim MiniLM instead of the model
        # the corpus was embedded with.
        query_embeddings=[get_embedding(question)],
        n_results=10,
        include=["documents", "metadatas", "distances"],
    )

    print("Query result:", result)


if __name__ == "__main__":
    run()
