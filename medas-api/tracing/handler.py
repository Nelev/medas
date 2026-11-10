"""One trace per agent run, built from what LangChain reports about it.

LangChain tells its callback handlers when a run starts and ends: the agent
(a graph), every model call, every tool call, and any step run by name. This
handler turns those into OpenTelemetry spans, named after the gen_ai semantic
conventions:

    invoke_agent medas              the agent run, the root of the trace
      chat <model>                  one per model call
      execute_tool <tool>           one per tool call
        retrieval <source>          the vector search inside a tool
        chat <model>                a model call a tool makes

What goes on a span is names, counts, model ids, token usage and the type of an
exception. Never a prompt, an answer, a tool's arguments or its result, a
passage or anything else that could be about a patient: the inputs and outputs
LangChain hands over are not read, except to count the passages a retrieval
returned and to see whether a tool reported a failure.
"""

import json
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from openai import OpenAIError
from opentelemetry import context, trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode, Tracer

AGENT = "medas"
# A step run under a name that starts like this is a retrieval, and the rest of
# the name is what it searched (rag_pipeline/search.py).
RETRIEVAL = "retrieval "
# What a tool that failed without raising is recorded as (see _reports_failure).
TOOL_REPORTED_ERROR = "ToolReportedError"
MESSAGE_MAX = 300


def _type_of(error: BaseException) -> str:
    kind = type(error)
    return f"{kind.__module__}.{kind.__qualname__}"


def _message_of(error: BaseException) -> str | None:
    """What the error says, only when it is safe to keep.

    A model provider's error is about the request as a whole (a status code, a
    context length), so it is kept, cut short. Any other exception may quote
    what it was given, which here can be a patient's text, so only its type is.
    """
    return str(error)[:MESSAGE_MAX] if isinstance(error, OpenAIError) else None


def _reports_failure(output: Any) -> bool:
    """Whether a tool that returned normally told the model it had failed.

    The tools catch what goes wrong with a source and answer the model with
    `{"error": ...}` instead of raising, so the run goes on. That is still a
    failed call, and the only sign of it is in the result.
    """
    content = getattr(output, "content", output)
    if not isinstance(content, str) or not content.startswith("{"):
        return False
    try:
        return "error" in json.loads(content)
    except ValueError:
        return False


class TraceHandler(BaseCallbackHandler):
    """Spans for the runs LangChain reports. One instance serves every request."""

    # Called in the event loop, in order, rather than handed to a thread: the
    # methods only touch memory, and a span must exist before its children start.
    run_inline = True

    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer
        self._spans: dict[UUID, Span] = {}
        # Every run's parent, spanned or not: a graph has steps of its own between
        # the agent and a model call, and a span hangs from the nearest one above.
        self._parents: dict[UUID, UUID | None] = {}
        self._retrievals: set[UUID] = set()

    def _start(
        self,
        run_id: UUID,
        parent_run_id: UUID | None,
        name: str,
        kind: SpanKind,
        attributes: dict[str, Any],
    ) -> None:
        self._parents[run_id] = parent_run_id
        above = parent_run_id
        while above is not None and above not in self._spans:
            above = self._parents.get(above)
        # An empty context for a run with nothing above it: a new trace, whatever
        # span the caller may happen to be in.
        parent = (
            trace.set_span_in_context(self._spans[above])
            if above is not None
            else context.Context()
        )
        self._spans[run_id] = self._tracer.start_span(
            name, context=parent, kind=kind, attributes=attributes
        )

    def _end(
        self,
        run_id: UUID,
        error_type: str | None = None,
        message: str | None = None,
    ) -> None:
        self._parents.pop(run_id, None)
        self._retrievals.discard(run_id)
        span = self._spans.pop(run_id, None)
        if span is None:
            return
        if error_type is not None:
            span.set_attribute("error.type", error_type)
            span.set_status(Status(StatusCode.ERROR, message))
        span.end()

    def _fail(self, run_id: UUID, error: BaseException) -> None:
        span = self._spans.get(run_id)
        message = _message_of(error)
        if span is not None:
            event = {"exception.type": _type_of(error)}
            if message is not None:
                event["exception.message"] = message
            span.add_event("exception", event)
        self._end(run_id, _type_of(error), message)

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        name = kwargs.get("name") or ""
        if name.startswith(RETRIEVAL):
            self._retrievals.add(run_id)
            self._start(
                run_id,
                parent_run_id,
                name,
                SpanKind.CLIENT,
                {
                    "gen_ai.operation.name": "retrieval",
                    "gen_ai.data_source.id": name.removeprefix(RETRIEVAL),
                },
            )
        elif parent_run_id is None:
            self._start(
                run_id,
                None,
                f"invoke_agent {AGENT}",
                SpanKind.SERVER,
                {"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": AGENT},
            )
        else:
            self._parents[run_id] = parent_run_id  # a step of the graph: no span

    def on_chain_end(self, outputs: Any, *, run_id: UUID, **kwargs: Any) -> None:
        if run_id in self._retrievals and isinstance(outputs, list):
            self._spans[run_id].set_attribute("retrieval.hits", len(outputs))
        self._end(run_id)

    def on_chain_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        self._fail(run_id, error)

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        described = metadata or {}
        model = described.get("ls_model_name") or "unknown"
        self._start(
            run_id,
            parent_run_id,
            f"chat {model}",
            SpanKind.CLIENT,
            {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": described.get("ls_provider") or "unknown",
                "gen_ai.request.model": model,
            },
        )

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        span = self._spans.get(run_id)
        answers = response.generations[0] if response.generations else []
        usage = getattr(getattr(answers[0], "message", None), "usage_metadata", None)
        if span is not None and usage:
            span.set_attribute("gen_ai.usage.input_tokens", usage["input_tokens"])
            span.set_attribute("gen_ai.usage.output_tokens", usage["output_tokens"])
        self._end(run_id)

    def on_llm_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        self._fail(run_id, error)

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        name = (serialized or {}).get("name") or kwargs.get("name") or "unknown"
        self._start(
            run_id,
            parent_run_id,
            f"execute_tool {name}",
            SpanKind.INTERNAL,
            {
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": name,
                "gen_ai.tool.type": "function",
            },
        )

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        self._end(run_id, TOOL_REPORTED_ERROR if _reports_failure(output) else None)

    def on_tool_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        self._fail(run_id, error)
