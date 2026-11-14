"""The agent's tools: the patient's record, documents, export and the two
public health sources. Each is a LangChain tool; `agent.build_agent` lists them.
"""

import json

import httpx
from langchain.tools import ToolRuntime, tool
from starlette.concurrency import run_in_threadpool

from database.database import open_session
from langchain_agent import health_sources
from langchain_agent.documents import add_document
from langchain_agent.export import export_turns
from langchain_agent.state import RecordState
from model import list_messages
from rag_pipeline.search import search_record
from schema import Attachment, Rejected


@tool
async def search_patient_record(
    query: str, runtime: ToolRuntime[None, RecordState]
) -> str:
    """Search the patient's medical record for passages relevant to a query."""
    # `runtime` is injected by LangChain and left out of the tool's schema, so
    # `query` is still the only argument the model sees: the record searched is
    # the caller's, and not one the model can ask for.
    passages = await search_record(query, runtime.state["record_id"])

    return json.dumps(passages)


def _attachments(runtime: ToolRuntime[None, RecordState]) -> tuple[Attachment, ...]:
    return runtime.state.get("attachments", ())


def _reply(document: str, status: str, **fields) -> str:
    # Only the status goes back to the model, never the document's text: the
    # file is untrusted, and this agent can write to the record.
    return json.dumps({"document": document, "status": status, **fields})


@tool
async def add_patient_document(
    document: str, runtime: ToolRuntime[None, RecordState]
) -> str:
    """Add a PDF the patient attached to this message to their record, once
    it is checked to be a medical document about them, so
    search_patient_record can find it. `document` is the attachment's file
    name."""
    attachments = _attachments(runtime)
    attachment = next((a for a in attachments if a.name == document), None)
    if attachment is None:
        attached = [a.name for a in attachments]
        return _reply(document, "not attached", attached=attached)
    try:
        chunks = await add_document(attachment, runtime.state["record_id"])
    except Rejected as exc:
        return _reply(document, "rejected", reason=str(exc))
    return _reply(document, "stored", chunks=chunks)


async def _stored_turns(runtime: ToolRuntime[None, RecordState]) -> list[dict]:
    """The conversation as the patient sees it, read from the database.

    The ids come from the run's state, so the model can export this
    conversation and no other, and the read is scoped to the user in the same
    statement. Empty when the run has no conversation, or it is gone.
    """
    user_id = runtime.state.get("user_id")
    conversation_id = runtime.state.get("conversation_id")
    if user_id is None or conversation_id is None:
        return []
    async with open_session() as session:
        stored = await list_messages(session, conversation_id, user_id=user_id)
    return [{"role": m["role"], "content": m["text"]} for m in stored]


@tool
async def export_conversation(
    runtime: ToolRuntime[None, RecordState], format: str = "pdf"
) -> str:
    """Export this conversation as a file, when the patient asks for it.
    `format` is csv, json or pdf; leave it out, or pass anything
    else, and the file is a PDF."""
    turns = await _stored_turns(runtime)
    if not turns:
        return json.dumps({"status": "no conversation"})
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
    except httpx.TimeoutException:
        # Said apart from the rest, and recorded on the trace
        # (tracing.handler.SAFE_TOOL_ERRORS): a slow source and a broken one
        # are fixed differently.
        return json.dumps({"error": "source timed out"})
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
