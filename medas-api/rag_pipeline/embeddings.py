import json
import os
from pathlib import Path

import chromadb
from chunks import iter_chunks
from const import OPENAI_BASE_URL
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")


MEDICAL_HISTORY_PATH = Path(__file__).parent / "medical_history.json"
CHROMA_PATH = Path(__file__).parent / "chroma"

with MEDICAL_HISTORY_PATH.open(encoding="utf-8") as f:
    document = json.load(f)

client = OpenAI(
    base_url=OPENAI_BASE_URL,
    api_key=OPENROUTER_API_KEY,
)

# Function to generate embeddings using OpenRouter
def get_embedding(input, model="openai/text-embedding-3-small"):
  rsp = client.embeddings.create(
      model=model,
      input=input
    )
  return rsp.data[0].embedding


# Batched variant: one request for many inputs, rather than one request each.
def get_embeddings_batch(inputs, model="openai/text-embedding-3-small"):
    rsp = client.embeddings.create(model=model, input=inputs)
    # The API is documented to return data in request order, but each item
    # carries its own index -- sort on it so a caller zipping the result back
    # against `inputs` cannot silently mispair text with vector.
    return [d.embedding for d in sorted(rsp.data, key=lambda d: d.index)]



if __name__ == "__main__":
    # Guarded: this makes a billable API call, so it must not fire
    # merely because something imported this module.
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
        n_results=1,
        include=["documents", "metadatas", "distances"],
    )

    print("Query result:", result)
