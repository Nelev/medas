"""Tests for how the agent is told which record to search.

No model and no vector store: the graph and search_record are stubbed, so
what is tested is the plumbing between the caller's record id and the search
the tool runs.
"""

import json
from types import SimpleNamespace

import pytest

import langchain_agent.agent as agent
from langchain_agent.agent import (
    RecordContext,
    add_patient_document,
    answer,
    search_patient_record,
)
from langchain_agent.documents import Attachment
from rag_pipeline.pdf import Rejected

RECORD_ID = "pat_7f3c9a21-4be8-4d0f-9c17-2a6e5b8d41f0"
LETTER = Attachment("letter.pdf", b"%PDF-1.4")


def test_the_model_can_only_pass_a_query():
    # The record comes from the run's context; if it were a tool argument the
    # model could search any record it named.
    schema = search_patient_record.tool_call_schema.model_json_schema()

    assert set(schema["properties"]) == {"query"}


async def test_the_tool_searches_the_record_in_the_runs_context(monkeypatch):
    searched = []

    async def _search_record(query, patient_id):
        searched.append((query, patient_id))
        return [{"chunk_id": "c1", "text": "Allergy: ibuprofen"}]

    monkeypatch.setattr(agent, "search_record", _search_record)
    runtime = SimpleNamespace(context=RecordContext(RECORD_ID))

    result = await search_patient_record.coroutine("allergies", runtime)

    assert searched == [("allergies", RECORD_ID)]
    assert "ibuprofen" in result


async def test_answer_runs_the_graph_with_the_callers_record(monkeypatch):
    invoked = []

    class _Graph:
        async def ainvoke(self, state, *, context):
            invoked.append((state, context))
            return {"messages": [SimpleNamespace(content="reply")]}

    monkeypatch.setattr(agent, "build_agent", _Graph)
    messages = [{"role": "user", "content": "Can I take ibuprofen?"}]

    assert await answer(messages, record_id=RECORD_ID) == ("reply", {})
    assert invoked == [({"messages": messages}, RecordContext(RECORD_ID))]


async def test_answer_hands_the_attachments_to_the_tools(monkeypatch):
    invoked = []

    class _Graph:
        async def ainvoke(self, state, *, context):
            invoked.append(context)
            return {
                "messages": [SimpleNamespace(content="reply")],
                "stored": {"letter.pdf": 3},
            }

    monkeypatch.setattr(agent, "build_agent", _Graph)

    result = await answer([], record_id=RECORD_ID, attachments=[LETTER])

    assert result == ("reply", {"letter.pdf": 3})
    assert invoked == [RecordContext(RECORD_ID, (LETTER,))]


def _runtime(attachments=(LETTER,)):
    return SimpleNamespace(
        context=RecordContext(RECORD_ID, attachments), tool_call_id="call_1"
    )


def _result(command) -> dict:
    """What the model is shown."""
    (message,) = command.update["messages"]
    assert message.tool_call_id == "call_1"
    return json.loads(message.content)


@pytest.fixture
def added(monkeypatch) -> list:
    """Stand in for langchain_agent.documents.add_document; returns the calls to it."""
    calls = []

    async def _add(attachment, record_id):
        calls.append((attachment, record_id))
        return 3

    monkeypatch.setattr(agent, "add_document", _add)
    return calls


def test_the_model_can_only_name_a_document():
    # The bytes and the record come from the run's context, not the model.
    schema = add_patient_document.tool_call_schema.model_json_schema()

    assert set(schema["properties"]) == {"document"}


async def test_an_attached_document_is_added(added):
    command = await add_patient_document.coroutine("letter.pdf", _runtime())

    assert _result(command) == {
        "document": "letter.pdf",
        "status": "stored",
        "chunks": 3,
    }
    # What answer's caller reads, rather than the model's word for it.
    assert command.update["stored"] == {"letter.pdf": 3}
    assert added == [(LETTER, RECORD_ID)]


async def test_a_rejected_document_is_not_reported_stored(monkeypatch):
    async def _add(*_):
        raise Rejected("not a medical document")

    monkeypatch.setattr(agent, "add_document", _add)

    command = await add_patient_document.coroutine("letter.pdf", _runtime())

    assert _result(command) == {
        "document": "letter.pdf",
        "status": "rejected",
        "reason": "not a medical document",
    }
    assert "stored" not in command.update


async def test_a_file_not_attached_cannot_be_named(added):
    command = await add_patient_document.coroutine("other.pdf", _runtime())

    assert _result(command) == {
        "document": "other.pdf",
        "status": "not attached",
        "attached": ["letter.pdf"],
    }
    assert added == []
