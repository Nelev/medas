"""Tests for how the agent is told which record to search.

No model and no vector store: the graph and search_record are stubbed, so
what is tested is the plumbing between the caller's record id and the search
the tool runs.
"""

from types import SimpleNamespace

import langchain_agent.agent as agent
from langchain_agent.agent import RecordContext, answer, search_patient_record

RECORD_ID = "pat_7f3c9a21-4be8-4d0f-9c17-2a6e5b8d41f0"


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

    reply = await answer(messages, record_id=RECORD_ID)

    assert reply == "reply"
    assert invoked == [({"messages": messages}, RecordContext(RECORD_ID))]
