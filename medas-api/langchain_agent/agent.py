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
import operator
import os
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, NamedTuple, NotRequired

from dotenv import load_dotenv
from langchain.agents import AgentState, create_agent
from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langchain_openai import ChatOpenAI
from langgraph.types import Command

from langchain_agent.assistant_general_prompt import ASSISTANT_SYSTEM_PROMPT
from langchain_agent.documents import Attachment, add_document
from rag_pipeline.pdf import Rejected
from rag_pipeline.search import search_record
from utils import OPENROUTER_BASE_URL

load_dotenv()

MODEL_NAME = "openai/gpt-4o-mini"


@dataclass(frozen=True)
class RecordContext:
    """Per-run data for the tools, passed at invoke time, never by the model."""

    record_id: str
    # The PDFs sent with this question, the only ones the document tools can
    # reach: the model names one, it cannot supply one.
    attachments: tuple[Attachment, ...] = ()


class RecordState(AgentState):
    """The run's state, which the model never sees: only messages reach it."""

    # Chunks written per attachment by add_patient_document: what a caller
    # reads to know a file was stored, rather than the model's word for it.
    # Merged, so two tool calls in one step do not overwrite each other.
    stored: NotRequired[Annotated[dict[str, int], operator.or_]]


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


def _reply(
    runtime: ToolRuntime,
    document: str,
    status: str,
    update: dict | None = None,
    **fields,
) -> Command:
    # Only the status goes back to the model, never the document's text: the
    # file is untrusted, and this agent can write to the record.
    result = {"document": document, "status": status, **fields}
    message = ToolMessage(json.dumps(result), tool_call_id=runtime.tool_call_id)
    return Command(update={"messages": [message], **(update or {})})


def _not_attached(runtime: ToolRuntime[RecordContext], document: str) -> Command:
    attached = [a.name for a in runtime.context.attachments]
    return _reply(runtime, document, "not attached", attached=attached)


@tool
async def add_patient_document(
    document: str, runtime: ToolRuntime[RecordContext]
) -> Command:
    """Add a PDF the patient attached to this message to their record, once
    it is checked to be a medical document about them, so
    search_patient_record can find it. `document` is the attachment's file
    name."""
    attachment = _attachment(runtime, document)
    if attachment is None:
        return _not_attached(runtime, document)
    try:
        chunks = await add_document(attachment, runtime.context.record_id)
    except Rejected as exc:
        return _reply(runtime, document, "rejected", reason=str(exc))
    return _reply(
        runtime, document, "stored", {"stored": {document: chunks}}, chunks=chunks
    )


class Answer(NamedTuple):
    reply: str
    # Chunks stored per attachment, read from the run's state: what the store
    # tool did, not the model's word for it.
    stored: dict[str, int]


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
        tools=[search_patient_record, add_patient_document],
        system_prompt=ASSISTANT_SYSTEM_PROMPT,
        state_schema=RecordState,
        context_schema=RecordContext,
    )


async def answer(
    messages: list[dict], *, record_id: str, attachments: Sequence[Attachment] = ()
) -> Answer:
    """Answer the last turn of `messages`, in the context of the ones before.

    The whole conversation goes in, oldest first, each turn a role and its
    content. The reply is the text of the last message the run produces.

    `record_id` is the record the search tool reads. Keyword-only and with no
    default, so a caller that forgets it fails rather than searching the
    wrong patient's record.

    `attachments` are the PDFs sent with the last turn, the only files the
    document tools can verify and store.
    """
    result = await build_agent().ainvoke(
        {"messages": messages},
        context=RecordContext(record_id, tuple(attachments)),
    )

    return Answer(result["messages"][-1].content, result.get("stored", {}))


async def main() -> None:
    result = await answer(
        [{"role": "user", "content": "Can I take ibuprofen?"}],
        # The seeded patient's record, the one the corpus holds.
        record_id="pat_7f3c9a21-4be8-4d0f-9c17-2a6e5b8d41f0",
    )
    print(result.reply)


if __name__ == "__main__":
    asyncio.run(main())
