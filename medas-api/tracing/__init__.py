"""Traces of what the agent does, for a tool that triages its failures.

Off unless OTEL_EXPORTER_OTLP_TRACES_ENDPOINT is set. See tracing/handler.py
for what a trace holds, and what it never does.
"""

from tracing.handler import TraceHandler
from tracing.runtime import (
    TracingMiddleware,
    active_handler,
    handler_for,
    start_tracing,
    stop_tracing,
    traced,
)
from tracing.settings import TracingSettings, get_tracing_settings

__all__ = [
    "TraceHandler",
    "TracingMiddleware",
    "TracingSettings",
    "active_handler",
    "get_tracing_settings",
    "handler_for",
    "start_tracing",
    "stop_tracing",
    "traced",
]
