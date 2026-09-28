import os
from functools import lru_cache

from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAI

from utils import OPENROUTER_BASE_URL

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

EMBEDDING_TIMEOUT_SECONDS = 20.0


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
        # An embedding is one short round trip; a request still running after
        # this is hung, and it is in the path of every record search.
        timeout=EMBEDDING_TIMEOUT_SECONDS,
    )


@lru_cache
def get_async_client() -> AsyncOpenAI:
    """The same client for callers already inside an event loop.

    Kept alongside the sync one rather than replacing it: rag_pipeline.run is
    a plain script with no loop to await in, and making it async would buy it
    nothing -- it embeds one batch and exits.
    """
    return AsyncOpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY,
        timeout=EMBEDDING_TIMEOUT_SECONDS,
    )


# Function to generate embeddings using OpenRouter
def get_embedding(input, model="openai/text-embedding-3-small"):
    rsp = get_client().embeddings.create(model=model, input=input)
    return rsp.data[0].embedding


async def get_embedding_async(input, model="openai/text-embedding-3-small"):
    """As above, awaited rather than blocking the caller's event loop."""
    rsp = await get_async_client().embeddings.create(model=model, input=input)
    return rsp.data[0].embedding


# Batched variant: one request for many inputs, rather than one request each.
def get_embeddings_batch(inputs, model="openai/text-embedding-3-small"):
    rsp = get_client().embeddings.create(model=model, input=inputs)
    # The API is documented to return data in request order, but each item
    # carries its own index -- sort on it so a caller zipping the result back
    # against `inputs` cannot silently mispair text with vector.
    return [d.embedding for d in sorted(rsp.data, key=lambda d: d.index)]
