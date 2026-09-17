import os

from dotenv import load_dotenv
from openai import OpenAI

from rag_pipeline.const import OPENAI_BASE_URL

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

client = OpenAI(
    base_url=OPENAI_BASE_URL,
    api_key=OPENROUTER_API_KEY,
)


# Function to generate embeddings using OpenRouter
def get_embedding(input, model="openai/text-embedding-3-small"):
    rsp = client.embeddings.create(model=model, input=input)
    return rsp.data[0].embedding


# Batched variant: one request for many inputs, rather than one request each.
def get_embeddings_batch(inputs, model="openai/text-embedding-3-small"):
    rsp = client.embeddings.create(model=model, input=inputs)
    # The API is documented to return data in request order, but each item
    # carries its own index -- sort on it so a caller zipping the result back
    # against `inputs` cannot silently mispair text with vector.
    return [d.embedding for d in sorted(rsp.data, key=lambda d: d.index)]
