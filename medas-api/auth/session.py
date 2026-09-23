"""The current user, from the Clerk session token on the request.

Two steps, as two dependencies, so each can be tested and overridden alone:
verify the token and read who it names (clerk_user_id), then find the users
row that person is (current_user).
"""

import uuid
from typing import Annotated

from clerk_backend_api import Clerk
from clerk_backend_api.security import (
    TokenVerificationError,
    TokenVerificationErrorReason,
    VerifyTokenOptions,
    verify_token_async,
)
from clerk_backend_api.security.types import TokenPrefix
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from auth.settings import AuthSettings, get_auth_settings
from database.database import get_session
from model import link_clerk_user, user_by_clerk_id

__all__ = ["CurrentUser", "clerk_user_id", "current_user", "verified_email"]

# auto_error=False so a missing header is our 401, with the same shape as a
# bad token, rather than FastAPI's own response.
_bearer = HTTPBearer(auto_error=False)

# verify_token_async also accepts API keys, OAuth and machine tokens, which it
# checks against Clerk's API. Those are for machines acting on their own
# behalf; this API only answers a person's session, so they are refused
# before verification rather than trusted after it.
_NOT_A_SESSION = tuple(prefix.value for prefix in TokenPrefix)

# Failures that are ours or Clerk's, not the caller's: retrying with the same
# token could succeed, so they are a 503 rather than a 401.
_UNAVAILABLE = {
    TokenVerificationErrorReason.JWK_FAILED_TO_LOAD,
    TokenVerificationErrorReason.SECRET_KEY_MISSING,
    TokenVerificationErrorReason.SERVER_ERROR,
}


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def clerk_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> str:
    """Clerk's id for the person whose session token this is."""
    if credentials is None:
        raise _unauthorized("Not signed in")

    token = credentials.credentials

    if token.startswith(_NOT_A_SESSION):
        raise _unauthorized("Not a session token")

    try:
        payload = await verify_token_async(
            token,
            VerifyTokenOptions(
                secret_key=settings.clerk_secret_key.get_secret_value(),
                jwt_key=settings.clerk_jwt_key,
                authorized_parties=settings.clerk_authorized_parties,
            ),
        )
    except TokenVerificationError as exc:
        if exc.reason in _UNAVAILABLE:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not verify the session",
            ) from exc
        raise _unauthorized("Invalid session token") from exc

    # A session token always names its session and its user. One without
    # either verified, but is not something this API knows how to answer.
    subject = payload.get("sub")
    if not payload.get("sid") or not isinstance(subject, str) or not subject:
        raise _unauthorized("Not a session token")

    return subject


async def verified_email(clerk_id: str, settings: AuthSettings) -> str | None:
    """The account's primary email, if Clerk has verified it.

    Only a verified address links an account to a user: an unverified one is
    just something the person typed, and linking on it would hand them
    whoever's record that address belongs to.
    """
    secret_key = settings.clerk_secret_key.get_secret_value()

    async with Clerk(bearer_auth=secret_key) as clerk:
        user = await clerk.users.get_async(user_id=clerk_id)

    for address in user.email_addresses:
        if address.id != user.primary_email_address_id:
            continue
        verification = address.verification
        if verification is not None and verification.status == "verified":
            return address.email_address

    return None


async def current_user(
    clerk_id: Annotated[str, Depends(clerk_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> uuid.UUID:
    """The id of the users row the signed-in person is.

    Linked by clerk_user_id after the first sign-in, which is one indexed
    lookup per request. On the first, the account's verified email is matched
    to an unclaimed row and the row is claimed. No match is a 403, not a new
    row: a user here is someone with a medical record, and signing up with
    Clerk does not give anyone one.
    """
    user_id = await user_by_clerk_id(session, clerk_id)
    if user_id is not None:
        return user_id

    email = await verified_email(clerk_id, settings)
    if email is not None:
        user_id = await link_clerk_user(session, clerk_id, email)

        if user_id is None:
            # Nothing to claim -- or a request racing this one just claimed
            # it for this same account. The second is no reason to refuse.
            user_id = await user_by_clerk_id(session, clerk_id)
        else:
            await session.commit()

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No record for this account",
        )

    return user_id


CurrentUser = Annotated[uuid.UUID, Depends(current_user)]
