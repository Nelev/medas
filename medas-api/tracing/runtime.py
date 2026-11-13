"""Turning tracing on for the app, and for each request.

LangChain picks up a callback handler from a context variable, so nothing that
builds or calls the agent has to know about tracing. A context variable set at
startup is not seen by the tasks that serve requests, so a middleware sets it
at the start of each one.
"""

import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from langchain_core.tracers.context import register_configure_hook
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.semconv.schemas import Schemas
from starlette.types import ASGIApp, Receive, Scope, Send

from tracing.handler import AGENT, TraceHandler
from tracing.settings import TracingSettings, get_tracing_settings

# The semantic conventions the span names and attributes follow (the gen_ai
# ones, with gen_ai.provider.name), sent with every trace as its schema URL.
SCHEMA_URL = Schemas.V1_37_0.value
PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"

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


def project_version(pyproject: Path = PYPROJECT) -> str | None:
    """The version in pyproject.toml, or None when the file is not there."""
    try:
        with pyproject.open("rb") as file:
            return tomllib.load(file)["project"]["version"]
    except OSError, KeyError, tomllib.TOMLDecodeError:
        return None


def resource(settings: TracingSettings) -> Resource:
    """What every trace says about where it came from: the app, its version
    and the conventions its spans follow."""
    attributes = {"service.name": AGENT}
    if version := settings.service_version or project_version():
        attributes["service.version"] = version
    return Resource(attributes, SCHEMA_URL)


def start_tracing() -> None:
    """Start exporting traces, if an endpoint is configured. Call once, at startup."""
    global _provider, _handler
    settings = get_tracing_settings()
    endpoint = settings.otel_exporter_otlp_traces_endpoint
    if not endpoint:
        return
    _provider = TracerProvider(resource=resource(settings))
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


def active_handler() -> TraceHandler | None:
    """The handler start_tracing made, or None while tracing is off.

    For code that runs the agent outside a request (a script), which the
    middleware never sees: it wraps its runs in `traced(handler)` itself.
    """
    return _handler


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
