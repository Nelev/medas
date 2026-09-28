import os
from functools import lru_cache

from dotenv import load_dotenv
from openai import OpenAI

from rag_pipeline.vector_store import EMBEDDING_MODEL, EMBEDDING_TIMEOUT_SECONDS
from utils import OPENROUTER_BASE_URL

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")


@lru_cache
def get_client() -> OpenAI:
    """Built on first use rather than at import.

    The SDK raises when the key is missing, so constructing it at import time
    makes merely importing this module require credentials -- which breaks
    anything that only wants the functions, CI included.
    """
    return OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY,
        timeout=EMBEDDING_TIMEOUT_SECONDS,
    )


# Function to generate embeddings using OpenRouter
def get_embedding(input, model=EMBEDDING_MODEL):
    rsp = get_client().embeddings.create(model=model, input=input)
    return rsp.data[0].embedding


# Batched variant: one request for many inputs, rather than one request each.
def get_embeddings_batch(inputs, model=EMBEDDING_MODEL):
    rsp = get_client().embeddings.create(model=model, input=inputs)
    # The API is documented to return data in request order, but each item
    # carries its own index -- sort on it so a caller zipping the result back
    # against `inputs` cannot silently mispair text with vector.
    return [d.embedding for d in sorted(rsp.data, key=lambda d: d.index)]
