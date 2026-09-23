"""The simplest LangChain agent: one tool, and whatever text it answers with.

Run it from medas-api:

    uv run python -m langchain_agent.agent

As a module, not a file: run as a file, this module's own name shadows the
`agent` package it imports search_record from.

The caller passes the whole conversation -- the stored turns and the new
question -- and gets back the model's reply as text. No schema, no memory of
its own, nothing it does not need to do that.
"""

import asyncio
import json
import os
from functools import lru_cache

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI

from agent.assistant_general_prompt import ASSISTANT_SYSTEM_PROMPT
from agent.search import search_record

load_dotenv()

MODEL_NAME = "openai/gpt-4o-mini"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# The one record this reads. A constant because there is one patient.
RECORD_ID = "pat_7f3c9a21-4be8-4d0f-9c17-2a6e5b8d41f0"


@tool
async def search_patient_record(query: str) -> str:
    """Search the patient's medical record for passages relevant to a query."""
    # `query` is the only argument, so the record searched is the one this
    # module names and not one the model can ask for.
    passages = await search_record(query, RECORD_ID)

    return json.dumps(passages)


@lru_cache
def build_agent():
    """The compiled graph, built on first call rather than at import.
    Lazy because constructing the model reads OPENROUTER_API_KEY, and an
    import that needs credentials is an import that fails in CI. Cached
    because the route calls this per request.
    """
    return create_agent(
        model=ChatOpenAI(
            model=MODEL_NAME,
            base_url=OPENROUTER_BASE_URL,
            api_key=os.getenv("OPENROUTER_API_KEY"),
            extra_body={"response_format": {"type": "json_object"}},
        ),
        tools=[search_patient_record],
        system_prompt=ASSISTANT_SYSTEM_PROMPT,
    )


async def answer(messages: list[dict]) -> str:
    """Answer the last turn of `messages`, in the context of the ones before.

    The whole conversation goes in, oldest first, each turn a role and its
    content. The reply is the text of the last message the run produces.
    """
    result = await build_agent().ainvoke({"messages": messages})

    return result["messages"][-1].content


async def main() -> None:
    print(await answer([{"role": "user", "content": "Can I take ibuprofen?"}]))


if __name__ == "__main__":
    asyncio.run(main())
