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
from collections.abc import Sequence
from functools import lru_cache

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.tools import ToolRuntime, tool
from langchain_openai import ChatOpenAI
from openai import OpenAIError
from starlette.concurrency import run_in_threadpool

from langchain_agent import health_sources
from langchain_agent.assistant_general_prompt import ASSISTANT_SYSTEM_PROMPT
from langchain_agent.documents import add_document
from langchain_agent.export import export_turns
from rag_pipeline.search import search_record
from schema import AgentUnavailable, Attachment, RecordContext, Rejected
from utils import OPENROUTER_BASE_URL

load_dotenv()

MODEL_NAME = "openai/gpt-4.1-mini"


@tool
async def search_patient_record(query: str, runtime: ToolRuntime[RecordContext]) -> str:
    """Search the patient's medical record for passages relevant to a query."""
    # `runtime` is injected by LangChain and left out of the tool's schema, so
    # `query` is still the only argument the model sees: the record searched is
    # the caller's, and not one the model can ask for.
    passages = await search_record(query, runtime.context.record_id)

    return json.dumps(passages)


def _attachment(
    runtime: ToolRuntime[RecordContext], document: str
) -> Attachment | None:
    return next((a for a in runtime.context.attachments if a.name == document), None)


def _reply(document: str, status: str, **fields) -> str:
    # Only the status goes back to the model, never the document's text: the
    # file is untrusted, and this agent can write to the record.
    return json.dumps({"document": document, "status": status, **fields})


@tool
async def add_patient_document(
    document: str, runtime: ToolRuntime[RecordContext]
) -> str:
    """Add a PDF the patient attached to this message to their record, once
    it is checked to be a medical document about them, so
    search_patient_record can find it. `document` is the attachment's file
    name."""
    attachment = _attachment(runtime, document)
    if attachment is None:
        attached = [a.name for a in runtime.context.attachments]
        return _reply(document, "not attached", attached=attached)
    try:
        chunks = await add_document(attachment, runtime.context.record_id)
    except Rejected as exc:
        return _reply(document, "rejected", reason=str(exc))
    return _reply(document, "stored", chunks=chunks)


@tool
async def export_conversation(
    runtime: ToolRuntime[RecordContext], format: str = "pdf"
) -> str:
    """Export this conversation as a file, when the patient asks for it.
    `format` is csv, json or pdf; leave it out, or pass anything
    else, and the file is a PDF."""
    # The turns come from the run's own state, so there is nothing for the
    # model to name: it can export this conversation and no other.
    turns = [
        {"role": "user" if m.type == "human" else "assistant", "content": m.content}
        for m in runtime.state["messages"]
        # Tool calls and their results are the agent's workings, not the chat.
        if m.type in ("human", "ai") and m.content
    ]
    file, used = await run_in_threadpool(export_turns, turns, format)
    return json.dumps(
        {
            "status": "exported",
            "file": file,
            "format": used,
            "requested": format,
            "turns": len(turns),
        }
    )


async def _lookup(source, query: str) -> str:
    try:
        return json.dumps(await source(query))
    except health_sources.SOURCE_ERRORS:
        # Say so, and let the model answer without it.
        return json.dumps({"error": "source unavailable"})


@tool
async def search_medlineplus(query: str) -> str:
    """Search MedlinePlus (US National Library of Medicine) for a plain-language
    explanation of a condition, symptom or medicine. Use one or two keywords,
    such as "ibuprofen", not a sentence. General information: it knows
    nothing about this patient, and `query` must never contain their name,
    date of birth or any identifier."""
    return await _lookup(health_sources.search_medlineplus, query)


@tool
async def search_pubmed(query: str) -> str:
    """Search PubMed for research articles (title, journal, year, abstract) on
    a medical question, such as an interaction between two drugs. General
    information: it knows nothing about this patient, and `query` must never
    contain their name, date of birth or any identifier."""
    return await _lookup(health_sources.search_pubmed, query)


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
        context_schema=RecordContext,
    )


async def answer(
    messages: list[dict], *, record_id: str, attachments: Sequence[Attachment] = ()
) -> str:
    """Answer the last turn of `messages`, in the context of the ones before.

    The whole conversation goes in, oldest first, each turn a role and its
    content. The reply is the text of the last message the run produces.

    `record_id` is the record the search tool reads. Keyword-only and with no
    default, so a caller that forgets it fails rather than searching the
    wrong patient's record.

    `attachments` are the PDFs sent with the last turn, the only files the
    document tools can verify and store.
    """
    try:
        result = await build_agent().ainvoke(
            {"messages": messages},
            context=RecordContext(record_id, tuple(attachments)),
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
