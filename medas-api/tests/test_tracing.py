"""Tracing: the spans an agent run leaves, and that none holds what a patient said.

No real model, no database and no collector: a scripted model drives the real
agent graph and real tools, and the spans are kept in memory.
"""

import json
from contextlib import suppress

import httpx
import openai
import pytest
from langchain.agents import create_agent
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

from rag_pipeline import search
from tracing import (
    TracingMiddleware,
    TracingSettings,
    get_tracing_settings,
    handler_for,
    runtime,
    start_tracing,
    stop_tracing,
    traced,
)

QUESTION = "Can I take ibuprofen with my blood pressure tablets?"
PASSAGE = "Allergy: penicillin. Reaction: rash."
USAGE = {"input_tokens": 120, "output_tokens": 30, "total_tokens": 150}


class ScriptedModel(GenericFakeChatModel):
    def bind_tools(self, tools, **_):
        return self


class UnreachableModel(ScriptedModel):
    def _generate(self, *args, **kwargs):
        raise openai.APITimeoutError(request=httpx.Request("POST", "https://x.test"))


class FakeStore:
    async def asimilarity_search_with_score(self, query, k, filter):
        return [
            (Document(id="c1", page_content=PASSAGE), 0.1),
            (Document(id="c2", page_content="Diagnosis: asthma."), 0.4),
        ]


@tool
async def record(query: str) -> str:
    """Search the patient's record."""
    return json.dumps(await search.search_record(query, "pat_1"))


@tool
async def unavailable(query: str) -> str:
    """A source that is down, and says so instead of raising."""
    return json.dumps({"error": "source unavailable"})


@tool
async def broken(query: str) -> str:
    """A tool whose error quotes what it was given."""
    raise ValueError(f"cannot read: {PASSAGE}")


@pytest.fixture
def exporter(monkeypatch):
    monkeypatch.setattr(search, "get_vector_store", FakeStore)
    return InMemorySpanExporter()


def calling(name: str) -> AIMessage:
    call = {"name": name, "args": {"query": QUESTION}, "id": "1"}
    return AIMessage(content="", tool_calls=[call], usage_metadata=USAGE)


async def run(exporter, model, *tools):
    """One agent run, traced into `exporter`. Returns its spans, oldest first."""
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    agent = create_agent(model=model, tools=list(tools))
    # When the run fails, its spans are what the test is about.
    with traced(handler_for(provider)), suppress(ValueError, openai.OpenAIError):
        await agent.ainvoke({"messages": [{"role": "user", "content": QUESTION}]})
    return sorted(exporter.get_finished_spans(), key=lambda span: span.start_time)


def scripted(*messages: AIMessage) -> ScriptedModel:
    return ScriptedModel(messages=iter(messages))


def named(spans, start: str):
    return [span for span in spans if span.name.startswith(start)]


async def test_a_run_is_one_trace_of_the_agent_its_model_calls_its_tool_and_the_retrieval(
    exporter,
):
    answer = AIMessage(content="No.", usage_metadata=USAGE)
    spans = await run(exporter, scripted(calling("record"), answer), record)

    (root,) = named(spans, "invoke_agent")
    (called,) = named(spans, "execute_tool")
    (retrieval,) = named(spans, "retrieval")
    chats = named(spans, "chat ")
    assert len(spans) == 5 and len(chats) == 2
    assert {span.context.trace_id for span in spans} == {root.context.trace_id}

    assert (root.name, root.parent, root.kind) == (
        "invoke_agent medas",
        None,
        SpanKind.SERVER,
    )
    assert root.resource.attributes.get("service.name") is not None
    for span in (called, *chats):
        assert span.parent.span_id == root.context.span_id
    assert called.name == "execute_tool record"
    assert called.attributes["gen_ai.operation.name"] == "execute_tool"

    # The retrieval hangs from the tool that made it, and counts what came back.
    assert retrieval.name == "retrieval record_chunks"
    assert retrieval.parent.span_id == called.context.span_id
    assert retrieval.attributes["gen_ai.operation.name"] == "retrieval"
    assert retrieval.attributes["retrieval.hits"] == 2

    assert chats[0].attributes["gen_ai.operation.name"] == "chat"
    assert chats[0].attributes["gen_ai.usage.input_tokens"] == 120
    assert chats[0].attributes["gen_ai.usage.output_tokens"] == 30
    assert all(span.status.status_code is not StatusCode.ERROR for span in spans)


async def test_a_tool_that_reports_a_failure_without_raising_is_a_failed_span(exporter):
    answer = AIMessage(content="I could not look that up.")
    spans = await run(exporter, scripted(calling("unavailable"), answer), unavailable)

    (called,) = named(spans, "execute_tool")
    assert called.status.status_code is StatusCode.ERROR
    assert called.attributes["error.type"] == "ToolReportedError"
    # The run went on and answered, so the request as a whole did not fail.
    (root,) = named(spans, "invoke_agent")
    assert root.status.status_code is not StatusCode.ERROR


async def test_a_tool_that_raises_leaves_its_exceptions_type_and_not_its_message(
    exporter,
):
    spans = await run(
        exporter, scripted(calling("broken"), AIMessage(content="")), broken
    )

    (called,) = named(spans, "execute_tool")
    assert called.status.status_code is StatusCode.ERROR
    assert called.attributes["error.type"] == "builtins.ValueError"
    assert called.status.description is None
    (event,) = called.events
    assert dict(event.attributes) == {"exception.type": "builtins.ValueError"}


async def test_a_model_providers_error_keeps_its_message_and_fails_the_run(exporter):
    spans = await run(exporter, UnreachableModel(messages=iter(())))

    (chat,) = named(spans, "chat ")
    (root,) = named(spans, "invoke_agent")
    for span in (chat, root):
        assert span.status.status_code is StatusCode.ERROR
        assert span.attributes["error.type"] == "openai.APITimeoutError"
        assert span.status.description == "Request timed out."


async def test_nothing_the_patient_or_the_record_said_is_on_any_span(exporter):
    answer = AIMessage(content=f"Your record says: {PASSAGE}")
    spans = await run(exporter, scripted(calling("record"), answer), record)
    spans += await run(exporter, scripted(calling("broken"), answer), broken)

    written = []
    for span in spans:
        written += [span.name, span.status.description, *span.attributes.values()]
        for event in span.events:
            written += [event.name, *event.attributes.values()]
    text = " ".join(str(value) for value in written)
    assert spans and QUESTION not in text and PASSAGE not in text
    assert "penicillin" not in text and "ibuprofen" not in text


async def test_with_tracing_off_the_search_is_a_plain_call(exporter):
    found = await search.search_record(QUESTION, "pat_1")

    assert [passage["chunk_id"] for passage in found] == ["c1", "c2"]
    assert exporter.get_finished_spans() == ()


async def test_the_middleware_traces_a_request_only_while_tracing_is_on(monkeypatch):
    seen = []

    async def app(scope, receive, send):
        seen.append(runtime._active.get())

    await TracingMiddleware(app)({"type": "http"}, None, None)
    handler = handler_for(TracerProvider())
    monkeypatch.setattr(runtime, "_handler", handler)
    await TracingMiddleware(app)({"type": "http"}, None, None)

    assert seen == [None, handler]
    assert runtime._active.get() is None  # and not after the request


def test_tracing_starts_only_with_an_endpoint(monkeypatch):
    start_tracing()
    assert runtime._handler is None  # conftest leaves the endpoint empty

    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://localhost:9/v1/traces"
    )
    get_tracing_settings.cache_clear()
    start_tracing()
    assert runtime._handler is not None

    stop_tracing()
    assert runtime._handler is None


def test_every_trace_names_the_app_its_version_and_its_conventions(tmp_path):
    made = runtime.resource(TracingSettings(service_version="abc1234"))
    assert made.attributes["service.name"] == "medas"
    assert made.attributes["service.version"] == "abc1234"
    assert made.schema_url == "https://opentelemetry.io/schemas/1.37.0"

    # Unset, the version comes from pyproject.toml; with no file, there is none.
    unset = runtime.resource(TracingSettings(service_version=None))
    assert unset.attributes["service.version"] == runtime.project_version()
    assert runtime.project_version(tmp_path / "missing.toml") is None


def test_the_export_carries_the_version_and_the_schema_url():
    exporter = InMemorySpanExporter()
    provider = TracerProvider(
        resource=runtime.resource(TracingSettings(service_version="abc1234"))
    )
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    provider.get_tracer("test").start_span("invoke_agent medas").end()

    (sent,) = encode_spans(exporter.get_finished_spans()).resource_spans
    assert sent.schema_url == "https://opentelemetry.io/schemas/1.37.0"
    attributes = {a.key: a.value.string_value for a in sent.resource.attributes}
    assert attributes["service.version"] == "abc1234"
