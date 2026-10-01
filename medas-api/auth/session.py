"""The current user, from the Clerk session token on the request.

Verify the token once (session_claims), then read from it who it names
(clerk_user_id) and the name the greeting addresses (greeting_name), and find
the users row that person is (current_user). Each is its own dependency, so
each can be tested and overridden alone; FastAPI runs session_claims once per
request however many depend on it.
"""

import uuid
from typing import Annotated, Any

from clerk_backend_api import Clerk
from clerk_backend_api.security import (
    TokenVerificationError,
    TokenVerificationErrorReason,
    VerifyTokenOptions,
    verify_token_async,
)
from clerk_backend_api.security.machine import get_token_type
from clerk_backend_api.security.types import TokenType
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from auth.settings import AuthSettings, get_auth_settings
from database.database import get_session
from model import create_clerk_user, link_clerk_user, user_by_clerk_id

__all__ = [
    "CurrentUser",
    "GreetingName",
    "clerk_user_id",
    "current_user",
    "greeting_name",
    "session_claims",
    "verified_email",
]

# auto_error=False so a missing header is our 401, with the same shape as a
# bad token, rather than FastAPI's own response.
_bearer = HTTPBearer(auto_error=False)

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


async def session_claims(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[AuthSettings, Depends(get_auth_settings)],
    request: Request,
) -> dict[str, Any]:
    """The claims of the request's session token, once it has verified."""
    if credentials is None:
        raise _unauthorized("Not signed in")

    token = credentials.credentials

    # verify_token_async also accepts API keys, OAuth and machine tokens, which
    # it checks against Clerk's API. Those are for machines acting on their own
    # behalf; this API only answers a person's session, so they are refused
    # before verification -- by the same classification the SDK dispatches on.
    if get_token_type(token) != TokenType.SESSION_TOKEN:
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

    # For the rate limiter, which keys on the verified user and sees only the
    # request.
    request.state.user_key = subject
    return payload


def clerk_user_id(
    claims: Annotated[dict[str, Any], Depends(session_claims)],
) -> str:
    """Clerk's id for the person whose session token this is."""
    return claims["sub"]


def greeting_name(
    claims: Annotated[dict[str, Any], Depends(session_claims)],
) -> str | None:
    """The name the greeting addresses: the account's first name.

    Read from the `first_name` claim, which the Clerk dashboard adds to the
    session token (Sessions -> Customize session token). Signed by Clerk like
    the rest of the token, and read locally -- no call to Clerk. Not who is
    asking: that is clerk_user_id. None for an account without a first name,
    or an instance without the claim configured; greeting_text decides what
    the greeting says then.
    """
    name = claims.get("first_name")
    if not isinstance(name, str):
        return None
    return name.strip() or None


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
    lookup per request. On the first, the account's verified email claims an
    unclaimed row with that address if there is one -- how a seeded user is
    signed in as -- and otherwise a row is created for the account.

    Still a 403 without a verified email, since the row needs one, or when
    the email already belongs to a row some other account has claimed.
    """
    user_id = await user_by_clerk_id(session, clerk_id)
    if user_id is not None:
        return user_id

    email = await verified_email(clerk_id, settings)
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No verified email for this account",
        )

    user_id = await link_clerk_user(session, clerk_id, email)
    if user_id is None:
        user_id = await create_clerk_user(session, clerk_id, email)

    if user_id is not None:
        await session.commit()
        return user_id

    # Neither claimed nor created: a request racing this one got there first
    # for this same account, which is no reason to refuse -- or the email is
    # another account's row, which is.
    user_id = await user_by_clerk_id(session, clerk_id)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This email belongs to another account",
        )

    return user_id


CurrentUser = Annotated[uuid.UUID, Depends(current_user)]
GreetingName = Annotated[str | None, Depends(greeting_name)]
