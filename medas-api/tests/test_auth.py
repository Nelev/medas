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
    "make_token",
    [
        pytest.param(lambda sign: sign(exp=int(time.time()) - 3600), id="expired"),
        pytest.param(
            lambda sign: sign(nbf=int(time.time()) + 3600), id="not-yet-valid"
        ),
        # Signed properly, but for some other site that uses Clerk.
        pytest.param(
            lambda sign: sign(azp="https://elsewhere.example"), id="other-azp"
        ),
        pytest.param(lambda sign: sign(azp=None), id="no-azp"),
        pytest.param(
            lambda sign: sign(
                key=rsa.generate_private_key(public_exponent=65537, key_size=2048)
            ),
            id="another-key",
        ),
        pytest.param(lambda sign: "not-a-jwt", id="garbage"),
    ],
)
async def test_a_token_that_fails_verification_is_401(settings, sign, make_token):
    with pytest.raises(HTTPException) as caught:
        await clerk_user_id(bearer(make_token(sign)), settings)

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
    """The three user statements, answered from dicts of rows."""

    def __init__(self, linked=None, unclaimed=None, taken=()) -> None:
        self.linked: dict[str, uuid.UUID] = dict(linked or {})
        # email -> user id, for rows no Clerk account has claimed yet.
        self.unclaimed: dict[str, uuid.UUID] = dict(unclaimed or {})
        # Emails of the rows in `linked`, which the INSERT must not reuse.
        self.taken = {email.lower() for email in taken}
        self.created: dict[str, uuid.UUID] = {}
        self.committed = False

    async def scalar(self, statement, params):
        sql = str(statement)
        if sql.startswith("UPDATE users"):
            user_id = self.unclaimed.pop(params["email"].lower(), None)
            if user_id is not None:
                self.linked[params["clerk_user_id"]] = user_id
            return user_id
        if sql.startswith("INSERT INTO users"):
            email, clerk_id = params["email"].lower(), params["clerk_user_id"]
            # ON CONFLICT DO NOTHING, on either unique column.
            if (
                email in self.taken
                or email in self.unclaimed
                or clerk_id in self.linked
            ):
                return None
            user_id = uuid.uuid4()
            self.linked[clerk_id] = self.created[clerk_id] = user_id
            self.taken.add(email)
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
    # Claimed, so nothing new was created alongside it.
    assert session.created == {}
    assert session.committed


async def test_an_account_matching_no_user_gets_a_new_one(settings, clerk_email):
    someone_else = uuid.uuid4()
    session = FakeSession(unclaimed={"someone.else@example.com": someone_else})

    user_id = await current_user(CLERK_ID, session, settings)

    assert session.created == {CLERK_ID: user_id}
    assert user_id != someone_else
    # Another address's unclaimed row is left for its own account.
    assert session.unclaimed == {"someone.else@example.com": someone_else}
    assert session.committed


async def test_the_created_user_is_found_by_its_account_afterwards(
    settings, clerk_email
):
    session = FakeSession()

    first = await current_user(CLERK_ID, session, settings)
    again = await current_user(CLERK_ID, session, settings)

    assert again == first
    # One row, and Clerk asked for the email only the first time.
    assert len(session.created) == 1
    assert clerk_email.calls == [CLERK_ID]


async def test_an_unverified_email_links_and_creates_nothing(settings, clerk_email):
    clerk_email.answer["email"] = None
    session = FakeSession(unclaimed={EMAIL: USER_ID})

    with pytest.raises(HTTPException) as caught:
        await current_user(CLERK_ID, session, settings)

    assert caught.value.status_code == 403
    assert caught.value.detail == "No verified email for this account"
    assert session.unclaimed == {EMAIL: USER_ID}
    assert session.created == {}
    assert not session.committed


async def test_a_user_claimed_by_another_account_is_not_taken(settings, clerk_email):
    # Same email, second Clerk account: the row is already someone's, and
    # a second row cannot have its address either.
    session = FakeSession(linked={"user_first": USER_ID}, taken={EMAIL})

    with pytest.raises(HTTPException) as caught:
        await current_user(CLERK_ID, session, settings)

    assert caught.value.status_code == 403
    assert caught.value.detail == "This email belongs to another account"
    assert session.linked == {"user_first": USER_ID}
    assert not session.committed


async def test_losing_the_race_to_create_yourself_is_not_a_403(settings, clerk_email):
    # Two first requests at once: the other linked or created the row for
    # this same account between the lookup and the writes.
    session = FakeSession()
    lookups = iter([None, USER_ID])

    async def scalar(statement, params):
        if str(statement).startswith(("UPDATE users", "INSERT INTO users")):
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


@pytest.mark.parametrize(
    ("status", "expected"),
    [("verified", EMAIL), ("unverified", None), (None, None)],
)
async def test_verified_email_is_the_primary_address_only_once_verified(
    settings, monkeypatch, status, expected
):
    # A verified secondary address never stands in for the primary one.
    user = SimpleNamespace(
        primary_email_address_id="idn_primary",
        email_addresses=[
            address("idn_other", "other@example.com", "verified"),
            address("idn_primary", EMAIL, status),
        ],
    )
    monkeypatch.setattr(auth.session, "Clerk", fake_clerk(user))

    assert await verified_email(CLERK_ID, settings) == expected
