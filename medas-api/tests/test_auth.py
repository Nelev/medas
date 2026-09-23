"""Tests for turning a Clerk session token into a user.

Tokens are real JWTs, signed here with a key generated for the run, and
verified by the SDK against its public half through clerk_jwt_key -- the
networkless path. So what is tested is the real verification, with nothing
of Clerk's reached over the network.
"""

import time
import uuid
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

import auth.session
from auth.session import clerk_user_id, current_user, verified_email
from auth.settings import AuthSettings

ORIGIN = "http://localhost:3000"
CLERK_ID = "user_2abcDEF"
USER_ID = uuid.UUID("7f3c9a21-4be8-4d0f-9c17-2a6e5b8d41f0")
EMAIL = "mattia@example.com"


@pytest.fixture(scope="module")
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def settings(signing_key) -> AuthSettings:
    public_pem = (
        signing_key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return AuthSettings(
        clerk_secret_key="sk_test_placeholder",
        clerk_jwt_key=public_pem,
        clerk_authorized_parties=[ORIGIN],
    )


@pytest.fixture
def sign(signing_key):
    """Mint a session token, with any claim overridden or dropped (None)."""

    def _sign(key=None, **overrides) -> str:
        now = int(time.time())
        claims = {
            "sub": CLERK_ID,
            "sid": "sess_123",
            "azp": ORIGIN,
            "iat": now,
            "nbf": now,
            "exp": now + 60,
            **overrides,
        }
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(claims, key or signing_key, algorithm="RS256")

    return _sign


def bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


async def test_a_valid_session_token_names_its_user(settings, sign):
    assert await clerk_user_id(bearer(sign()), settings) == CLERK_ID


async def test_no_token_is_401_with_a_bearer_challenge(settings):
    with pytest.raises(HTTPException) as caught:
        await clerk_user_id(None, settings)

    assert caught.value.status_code == 401
    assert caught.value.headers == {"WWW-Authenticate": "Bearer"}


@pytest.mark.parametrize(
    "claims",
    [
        pytest.param({"exp": int(time.time()) - 3600}, id="expired"),
        pytest.param({"nbf": int(time.time()) + 3600}, id="not-yet-valid"),
        # Signed properly, but for some other site that uses Clerk.
        pytest.param({"azp": "https://elsewhere.example"}, id="other-azp"),
        pytest.param({"azp": None}, id="no-azp"),
    ],
)
async def test_a_token_that_fails_verification_is_401(settings, sign, claims):
    with pytest.raises(HTTPException) as caught:
        await clerk_user_id(bearer(sign(**claims)), settings)

    assert caught.value.status_code == 401


async def test_a_token_signed_by_another_key_is_401(settings, sign):
    stranger = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    with pytest.raises(HTTPException) as caught:
        await clerk_user_id(bearer(sign(key=stranger)), settings)

    assert caught.value.status_code == 401


async def test_garbage_is_401(settings):
    with pytest.raises(HTTPException) as caught:
        await clerk_user_id(bearer("not-a-jwt"), settings)

    assert caught.value.status_code == 401


@pytest.mark.parametrize("claim", ["sid", "sub"])
async def test_a_verified_token_without_a_session_or_user_is_401(settings, sign, claim):
    # Good signature, not a session token: nothing here to answer for.
    with pytest.raises(HTTPException) as caught:
        await clerk_user_id(bearer(sign(**{claim: None})), settings)

    assert caught.value.status_code == 401


@pytest.mark.parametrize("prefix", ["ak_", "oat_", "m2m_", "mt_"])
async def test_machine_tokens_are_refused_without_asking_clerk(
    settings, monkeypatch, prefix
):
    # The SDK would check these against Clerk's API; they are refused first.
    async def _must_not_run(*args, **kwargs):
        raise AssertionError("verify_token_async was called")

    monkeypatch.setattr(auth.session, "verify_token_async", _must_not_run)

    with pytest.raises(HTTPException) as caught:
        await clerk_user_id(bearer(f"{prefix}secret"), settings)

    assert caught.value.status_code == 401


class FakeSession:
    """The two user statements, answered from a dict of linked accounts."""

    def __init__(self, linked=None, unclaimed=None) -> None:
        self.linked: dict[str, uuid.UUID] = dict(linked or {})
        # email -> user id, for rows no Clerk account has claimed yet.
        self.unclaimed: dict[str, uuid.UUID] = dict(unclaimed or {})
        self.committed = False

    async def scalar(self, statement, params):
        sql = str(statement)
        if sql.startswith("UPDATE users"):
            user_id = self.unclaimed.pop(params["email"].lower(), None)
            if user_id is not None:
                self.linked[params["clerk_user_id"]] = user_id
            return user_id
        return self.linked.get(params["clerk_user_id"])

    async def commit(self) -> None:
        self.committed = True


@pytest.fixture
def clerk_email(monkeypatch):
    """Stand in for the Clerk lookup.

    Records the ids asked about, and answers with `answer["email"]`, which a
    test can change.
    """
    looked_up: list[str] = []
    answer = {"email": EMAIL}

    async def _verified_email(clerk_id, settings):
        looked_up.append(clerk_id)
        return answer["email"]

    monkeypatch.setattr(auth.session, "verified_email", _verified_email)
    return SimpleNamespace(calls=looked_up, answer=answer)


async def test_a_linked_account_is_its_user_without_asking_clerk(settings, clerk_email):
    session = FakeSession(linked={CLERK_ID: USER_ID})

    assert await current_user(CLERK_ID, session, settings) == USER_ID
    assert clerk_email.calls == []


async def test_the_first_sign_in_claims_the_user_with_that_email(settings, clerk_email):
    session = FakeSession(unclaimed={EMAIL: USER_ID})

    assert await current_user(CLERK_ID, session, settings) == USER_ID
    assert session.linked == {CLERK_ID: USER_ID}
    assert session.committed


async def test_an_account_matching_no_user_is_403(settings, clerk_email):
    session = FakeSession(unclaimed={"someone.else@example.com": uuid.uuid4()})

    with pytest.raises(HTTPException) as caught:
        await current_user(CLERK_ID, session, settings)

    assert caught.value.status_code == 403
    assert caught.value.detail == "No record for this account"
    # Refused, not created: nothing was written.
    assert session.linked == {}
    assert not session.committed


async def test_an_unverified_email_links_nothing(settings, clerk_email):
    clerk_email.answer["email"] = None
    session = FakeSession(unclaimed={EMAIL: USER_ID})

    with pytest.raises(HTTPException) as caught:
        await current_user(CLERK_ID, session, settings)

    assert caught.value.status_code == 403
    assert session.unclaimed == {EMAIL: USER_ID}


async def test_a_user_claimed_by_another_account_is_not_taken(settings, clerk_email):
    # Same email, second Clerk account: the row is already someone's.
    session = FakeSession(linked={"user_first": USER_ID})

    with pytest.raises(HTTPException) as caught:
        await current_user(CLERK_ID, session, settings)

    assert caught.value.status_code == 403
    assert session.linked == {"user_first": USER_ID}


async def test_losing_the_race_to_link_yourself_is_not_a_403(settings, clerk_email):
    # Two first requests at once: the other claimed the row for this same
    # account between the lookup and the UPDATE.
    session = FakeSession()
    lookups = iter([None, USER_ID])

    async def scalar(statement, params):
        if str(statement).startswith("UPDATE users"):
            return None
        return next(lookups)

    session.scalar = scalar

    assert await current_user(CLERK_ID, session, settings) == USER_ID


def fake_clerk(user):
    """Replace the SDK client with one that returns `user` for any id."""

    class _Users:
        async def get_async(self, *, user_id):
            return user

    class _Clerk:
        def __init__(self, bearer_auth):
            self.users = _Users()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

    return _Clerk


def address(id_, email, status):
    return SimpleNamespace(
        id=id_,
        email_address=email,
        verification=None if status is None else SimpleNamespace(status=status),
    )


async def test_verified_email_is_the_primary_verified_address(settings, monkeypatch):
    user = SimpleNamespace(
        primary_email_address_id="idn_primary",
        email_addresses=[
            address("idn_other", "other@example.com", "verified"),
            address("idn_primary", EMAIL, "verified"),
        ],
    )
    monkeypatch.setattr(auth.session, "Clerk", fake_clerk(user))

    assert await verified_email(CLERK_ID, settings) == EMAIL


@pytest.mark.parametrize("status", ["unverified", None])
async def test_an_unverified_primary_address_is_no_email(settings, monkeypatch, status):
    # And a verified secondary does not stand in for it.
    user = SimpleNamespace(
        primary_email_address_id="idn_primary",
        email_addresses=[
            address("idn_primary", EMAIL, status),
            address("idn_other", "other@example.com", "verified"),
        ],
    )
    monkeypatch.setattr(auth.session, "Clerk", fake_clerk(user))

    assert await verified_email(CLERK_ID, settings) is None
