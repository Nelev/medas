"""The fault switches: off unless set, and each breaks what it says it breaks.

No model, no database and no network: the agent graph runs on a scripted model
where a fault needs it, and the search and the sources are stubbed.
"""

from types import SimpleNamespace

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from pydantic import ValidationError

import faults
import langchain_agent.agent as agent
import langchain_agent.health_sources as sources
import langchain_agent.tools as tools
from faults import FaultMiddleware, FaultSettings
from langchain_agent.assistant_general_prompt import ASSISTANT_SYSTEM_PROMPT
from langchain_agent.state import RecordState
from rag_pipeline import search
from tracing import handler_for, traced


def settings(**on) -> FaultSettings:
    return FaultSettings(_env_file=None, **on)


def switch_on(monkeypatch, **on) -> None:
    monkeypatch.setattr(faults, "get_faults", lambda: settings(**on))


def test_every_fault_is_off_by_default():
    assert settings().active() == []


def test_the_faults_that_are_on_are_named():
    on = settings(tool_schema=True, upstream_timeout=0.5, context_tokens=800)

    assert on.active() == ["tool_schema", "context_tokens", "upstream_timeout"]


def test_the_switches_are_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("FAULT_EMPTY_RETRIEVAL", "allergy")
    monkeypatch.setenv("FAULT_UPSTREAM_TIMEOUT", "0.25")

    read = FaultSettings(_env_file=None)

    assert (read.empty_retrieval, read.upstream_timeout) == ("allergy", 0.25)


@pytest.mark.parametrize(
    "bad",
    [{"empty_retrieval": "surgery"}, {"upstream_timeout": 1.5}, {"context_tokens": 0}],
)
def test_a_switch_set_to_nonsense_is_refused(bad):
    with pytest.raises(ValidationError):
        settings(**bad)


@pytest.mark.parametrize(
    ("query", "category"),
    [
        ("current medications", "medication"),
        ("Dupilumab injection dose", "medication"),
        ("known allergies", "allergy"),
        ("next ENT follow-up", "appointment"),
        ("asthma history", None),
    ],
)
def test_a_search_is_put_in_a_category_by_its_words(query, category):
    assert faults.category_of(query) == category


class Store:
    def __init__(self):
        self.searched = []

    async def asimilarity_search_with_score(self, query, k, filter):
        self.searched.append(query)
        return [(SimpleNamespace(id="c1", page_content="passage"), 0.1)]


async def test_empty_retrieval_finds_nothing_for_its_category_only(monkeypatch):
    store = Store()
    monkeypatch.setattr(search, "get_vector_store", lambda: store)
    switch_on(monkeypatch, empty_retrieval="medication")

    emptied = await search.search_record("current medications", "pat_1")
    found = await search.search_record("asthma history", "pat_1")

    assert emptied == []
    assert [p["chunk_id"] for p in found] == ["c1"]
    assert store.searched == ["asthma history"]


def test_the_truncated_prompt_loses_its_output_section(monkeypatch):
    switch_on(monkeypatch, truncated_prompt=True)

    cut = faults.truncated(ASSISTANT_SYSTEM_PROMPT)

    assert faults.PROMPT_CUT_AT in ASSISTANT_SYSTEM_PROMPT
    assert ASSISTANT_SYSTEM_PROMPT.startswith(cut)
    assert faults.PROMPT_CUT_AT not in cut


def test_the_prompt_is_whole_while_the_switch_is_off():
    assert faults.truncated(ASSISTANT_SYSTEM_PROMPT) == ASSISTANT_SYSTEM_PROMPT


def test_the_agent_is_built_with_the_faults_that_are_on(monkeypatch):
    built = {}
    monkeypatch.setattr(agent, "ChatOpenAI", lambda **kw: kw)
    monkeypatch.setattr(agent, "create_agent", lambda **kw: built.update(kw))
    switch_on(monkeypatch, weak_model="vendor/small", truncated_prompt=True)
    agent.build_agent.cache_clear()
    try:
        agent.build_agent()
    finally:
        agent.build_agent.cache_clear()

    assert built["model"]["model"] == "vendor/small"
    assert faults.PROMPT_CUT_AT not in built["system_prompt"]
    assert any(isinstance(m, FaultMiddleware) for m in built["middleware"])


@pytest.mark.parametrize(("share", "expected"), [(0.0, False), (1.0, True)])
def test_upstream_timeout_times_out_its_share_of_calls(monkeypatch, share, expected):
    switch_on(monkeypatch, upstream_timeout=share)

    assert faults.times_out() is expected


async def test_a_timed_out_call_gets_the_short_timeout(monkeypatch):
    given = []

    class Client:
        def __init__(self, timeout):
            given.append(timeout)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, params):
            return SimpleNamespace(raise_for_status=lambda: None)

    monkeypatch.setattr(sources.httpx, "AsyncClient", Client)
    switch_on(monkeypatch, upstream_timeout=1.0)

    await sources._get("https://x.test", {})

    assert given == [faults.TIMED_OUT_S]


def question(text="q"):
    return HumanMessage(text)


def call(n):
    return AIMessage("", tool_calls=[{"name": "t", "args": {}, "id": str(n)}])


def result(n, size):
    return ToolMessage("x" * size, tool_call_id=str(n))


def test_a_short_thread_fits_the_budget_whole():
    thread = [question(), call(1), result(1, 40)]

    assert faults.within(thread, 100) == thread


def test_a_long_result_is_dropped_with_its_call_and_the_question_kept():
    thread = [question("earlier"), AIMessage("a"), question(), call(1), result(1, 4000)]

    assert faults.within(thread, 100) == thread[:3]


def test_what_fits_after_a_long_result_is_kept():
    thread = [question(), call(1), result(1, 4000), call(2), result(2, 40)]

    assert faults.within(thread, 100) == [thread[0], *thread[3:]]


class Request:
    def __init__(self, **fields):
        self.__dict__.update(fields)

    def override(self, **changes):
        return Request(**{**self.__dict__, **changes})


async def _sent(request):
    return request


async def test_the_context_budget_trims_what_the_model_is_sent():
    thread = [question(), call(1), result(1, 4000)]
    middleware = FaultMiddleware(settings(context_tokens=100))

    sent = await middleware.awrap_model_call(Request(messages=thread), _sent)

    assert sent.messages == [thread[0]]


async def test_with_every_fault_off_the_middleware_changes_nothing():
    middleware = FaultMiddleware(settings())
    model_request = Request(messages=[question(), call(1), result(1, 4000)])
    tool_request = Request(
        tool_call={"name": faults.BROKEN_TOOL, "args": {"query": "q"}}
    )

    assert await middleware.awrap_model_call(model_request, _sent) is model_request
    assert await middleware.awrap_tool_call(tool_request, _sent) is tool_request


async def test_the_broken_schema_renames_the_record_searchs_argument_only():
    middleware = FaultMiddleware(settings(tool_schema=True))

    def request(name):
        return Request(tool_call={"name": name, "args": {"query": "q"}, "id": "1"})

    broken = await middleware.awrap_tool_call(request(faults.BROKEN_TOOL), _sent)
    other = await middleware.awrap_tool_call(request("search_pubmed"), _sent)

    assert broken.tool_call["args"] == {faults.STALE_ARGUMENT: "q"}
    assert other.tool_call["args"] == {"query": "q"}


class ScriptedModel(GenericFakeChatModel):
    def bind_tools(self, tools, **_):
        return self


async def test_the_broken_schema_fails_the_tool_call_and_the_run_goes_on(
    monkeypatch,
):
    searched = []

    async def _search_record(query, patient_id):
        searched.append(query)
        return []

    monkeypatch.setattr(tools, "search_record", _search_record)
    asked = {"name": faults.BROKEN_TOOL, "args": {"query": "medications"}, "id": "1"}
    model = ScriptedModel(
        messages=iter([AIMessage("", tool_calls=[asked]), AIMessage("{}")])
    )
    graph = create_agent(
        model=model,
        tools=[tools.search_patient_record],
        middleware=[FaultMiddleware(settings(tool_schema=True))],
        state_schema=RecordState,
    )
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    with traced(handler_for(provider)):
        result = await graph.ainvoke(
            {"messages": [question("What do I take?")], "record_id": "pat_1"}
        )

    assert searched == []
    assert result["messages"][2].status == "error"
    (span,) = [
        s for s in exporter.get_finished_spans() if s.name.startswith("execute_tool")
    ]
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes["error.type"].endswith("ValidationError")
