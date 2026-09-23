from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    """Clerk settings, read from the environment or .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # The same secret key the UI has. It fetches the public keys tokens are
    # verified against, and looks up a user's email on their first sign-in.
    clerk_secret_key: SecretStr

    # A PEM public key, to verify tokens without a network call. Optional:
    # without it the key is fetched from Clerk with the secret key and
    # cached. The tests use it with a key they generate.
    clerk_jwt_key: str | None = None

    # The origins a token may have been issued for (its azp claim). A token
    # minted for some other site that uses Clerk is refused even though its
    # signature is good. A JSON list in the environment.
    clerk_authorized_parties: list[str] = ["http://localhost:3000"]


@lru_cache
def get_auth_settings() -> AuthSettings:
    return AuthSettings()
