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
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.tools import ToolRuntime, tool
from langchain_openai import ChatOpenAI

from agent.assistant_general_prompt import ASSISTANT_SYSTEM_PROMPT
from agent.search import search_record

load_dotenv()

MODEL_NAME = "openai/gpt-4o-mini"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass(frozen=True)
class RecordContext:
    """Per-run data for the tools, passed at invoke time, never by the model."""

    record_id: str


@tool
async def search_patient_record(query: str, runtime: ToolRuntime[RecordContext]) -> str:
    """Search the patient's medical record for passages relevant to a query."""
    # `runtime` is injected by LangChain and left out of the tool's schema, so
    # `query` is still the only argument the model sees: the record searched is
    # the caller's, and not one the model can ask for.
    passages = await search_record(query, runtime.context.record_id)

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
        context_schema=RecordContext,
    )


async def answer(messages: list[dict], *, record_id: str) -> str:
    """Answer the last turn of `messages`, in the context of the ones before.

    The whole conversation goes in, oldest first, each turn a role and its
    content. The reply is the text of the last message the run produces.

    `record_id` is the record the search tool reads. Keyword-only and with no
    default, so a caller that forgets it fails rather than searching the
    wrong patient's record.
    """
    result = await build_agent().ainvoke(
        {"messages": messages}, context=RecordContext(record_id)
    )

    return result["messages"][-1].content


async def main() -> None:
    print(
        await answer(
            [{"role": "user", "content": "Can I take ibuprofen?"}],
            # The seeded patient's record, the one the corpus holds.
            record_id="pat_7f3c9a21-4be8-4d0f-9c17-2a6e5b8d41f0",
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
