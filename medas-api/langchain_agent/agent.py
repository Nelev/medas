"""The LangChain agent: a search tool, a document tool, and its reply.

Run it from medas-api:

    uv run python -m langchain_agent.agent

The caller passes the whole conversation -- the stored turns and the new
question -- and gets back the model's reply as text: a JSON object, as the
prompt asks for, which the caller reads with utils.parse_agent_reply. No
memory of its own, nothing it does not need to do that.
"""

import asyncio
import json
import os
import uuid
from collections.abc import Sequence
from functools import lru_cache

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from openai import OpenAIError

from langchain_agent.assistant_general_prompt import ASSISTANT_SYSTEM_PROMPT
from langchain_agent.middleware import MessageTrimmingMiddleware
from langchain_agent.state import RecordState
from langchain_agent.tools import (
    add_patient_document,
    export_conversation,
    search_medlineplus,
    search_patient_record,
    search_pubmed,
)
from schema import AgentUnavailable, Attachment
from utils import OPENROUTER_BASE_URL

load_dotenv()

MODEL_NAME = "openai/gpt-4.1-mini"


SOURCE_TOOLS = {"search_medlineplus", "search_pubmed"}
SOURCES_PER_LOOKUP = 2


def _source_urls(messages: list) -> list[str]:
    """The pages the run's lookups returned, best first, once each. Taken from
    the tool results rather than from the model: it is not reliable at citing,
    and these are the only pages it was shown."""
    urls = []
    for m in messages:
        if m.type == "tool" and m.name in SOURCE_TOOLS:
            found = json.loads(m.content)
            if isinstance(found, list):
                urls += [r["url"] for r in found[:SOURCES_PER_LOOKUP]]
    return list(dict.fromkeys(urls))


def _with_sources(reply: object, urls: list[str]) -> object:
    """`reply` with the pages listed at the end of its message, or of the
    text when the model answered in prose."""
    if not urls or not isinstance(reply, str):
        return reply
    block = "\n\nSources:\n" + "\n".join(f"- {url}" for url in urls)
    try:
        answer = json.loads(reply)
        answer["message"] += block
    except json.JSONDecodeError, KeyError, TypeError:
        return reply + block
    return json.dumps(answer)


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
        tools=[
            search_patient_record,
            add_patient_document,
            export_conversation,
            search_medlineplus,
            search_pubmed,
        ],
        system_prompt=ASSISTANT_SYSTEM_PROMPT,
        middleware=[MessageTrimmingMiddleware()],
        state_schema=RecordState,
    )


async def answer(
    messages: list[dict],
    *,
    record_id: str,
    user_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
    attachments: Sequence[Attachment] = (),
) -> str:
    """Answer the last turn of `messages`, in the context of the ones before.

    The whole conversation goes in, oldest first, each turn a role and its
    content. The reply is the text of the last message the run produces.

    `record_id` is the record the search tool reads. Keyword-only and with no
    default, so a caller that forgets it fails rather than searching the
    wrong patient's record.

    `user_id` and `conversation_id` say which stored conversation the export
    tool may read; without them it has nothing to export.

    `attachments` are the PDFs sent with the last turn, the only files the
    document tools can verify and store.
    """
    try:
        result = await build_agent().ainvoke(
            {
                "messages": messages,
                "record_id": record_id,
                "attachments": tuple(attachments),
                "user_id": user_id,
                "conversation_id": conversation_id,
            }
        )
    except OpenAIError as exc:
        raise AgentUnavailable from exc

    messages = result["messages"]
    return _with_sources(messages[-1].content, _source_urls(messages))


async def main() -> None:
    result = await answer(
        [{"role": "user", "content": "Can I take ibuprofen?"}],
        # The seeded patient's record, the one the corpus holds.
        record_id="pat_7f3c9a21-4be8-4d0f-9c17-2a6e5b8d41f0",
    )
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
