from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    """Application settings, read from the environment or .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_host: str = "localhost"
    database_port: int = 5432
    database_user: str = "medas"
    # SecretStr keeps the value out of tracebacks and repr() output.
    database_password: SecretStr
    database_name: str = "medas"

    db_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_timeout: int = 10

    @property
    def database_url(self) -> URL:
        """Async DSN. URL.create escapes the password, so characters like
        @ : / % in it need no hand-encoding."""
        return URL.create(
            "postgresql+asyncpg",
            username=self.database_user,
            password=self.database_password.get_secret_value(),
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
        )


@lru_cache
def get_settings() -> Settings:
    # database_password has no default, so pyright sees a missing argument.
    # It is supplied at runtime from the environment or .env, which the type
    # checker cannot see. Raises ValidationError if it is genuinely absent.
    return Settings()  # pyright: ignore[reportCallIssue]
