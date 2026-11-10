"""Turning tracing on for the app, and for each request.

LangChain picks up a callback handler from a context variable, so nothing that
builds or calls the agent has to know about tracing. A context variable set at
startup is not seen by the tasks that serve requests, so a middleware sets it
at the start of each one.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from langchain_core.tracers.context import register_configure_hook
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from starlette.types import ASGIApp, Receive, Scope, Send

from tracing.handler import AGENT, TraceHandler
from tracing.settings import get_tracing_settings

_active: ContextVar[TraceHandler | None] = ContextVar("medas_tracing", default=None)
# Every run LangChain starts, and every run below it, gets the handler in the
# variable, when there is one. Registering makes no call and starts nothing.
register_configure_hook(_active, inheritable=True)

_provider: TracerProvider | None = None
_handler: TraceHandler | None = None


@contextmanager
def traced(handler: TraceHandler) -> Iterator[None]:
    """Trace the agent runs made inside the block with `handler`."""
    token = _active.set(handler)
    try:
        yield
    finally:
        _active.reset(token)


def handler_for(provider: TracerProvider) -> TraceHandler:
    return TraceHandler(provider.get_tracer("medas.tracing"))


def start_tracing() -> None:
    """Start exporting traces, if an endpoint is configured. Call once, at startup."""
    global _provider, _handler
    endpoint = get_tracing_settings().otel_exporter_otlp_traces_endpoint
    if not endpoint:
        return
    _provider = TracerProvider(resource=Resource({"service.name": AGENT}))
    # Spans are sent in batches from a background thread, so a request never
    # waits for the collector, and a collector that is down loses spans, not
    # requests.
    _provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
    )
    _handler = handler_for(_provider)


def stop_tracing() -> None:
    """Send what is still waiting and stop. Call once, at shutdown."""
    global _provider, _handler
    if _provider is not None:
        _provider.shutdown()
    _provider = _handler = None


class TracingMiddleware:
    """Makes the handler the one LangChain uses for the length of a request."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if _handler is None:
            await self._app(scope, receive, send)
            return
        with traced(_handler):
            await self._app(scope, receive, send)
