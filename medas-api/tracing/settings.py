from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class TracingSettings(BaseSettings):
    """Where traces go, read from the environment or .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # The OTLP/HTTP endpoint that takes traces, for example TraceScan's
    # collector at http://localhost:8010/v1/traces. Unset, the usual case,
    # means no tracing at all: no spans are made and nothing is sent.
    otel_exporter_otlp_traces_endpoint: str | None = None


@lru_cache
def get_tracing_settings() -> TracingSettings:
    return TracingSettings()
