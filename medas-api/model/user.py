"""The user model."""

import datetime
import enum
import uuid

from sqlalchemy import DateTime, Enum, String, Uuid, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base

__all__ = [
    "User",
    "UserRole",
    "create_clerk_user",
    "link_clerk_user",
    "user_by_clerk_id",
]


class UserRole(enum.StrEnum):
    USER = "user"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        # gen_random_uuid() is core Postgres since 13 -- no pgcrypto needed.
        server_default=text("gen_random_uuid()"),
    )

    # 320 is the longest legal address (64 local + @ + 255 domain).
    # unique=True already gives Postgres a unique index; don't add index=True too.
    email: Mapped[str] = mapped_column(String(320), unique=True)

    # Clerk's id for the person signed in as this user. Null until their
    # first sign-in links it; see the migration that added it.
    clerk_user_id: Mapped[str | None] = mapped_column(String(64), unique=True)

    role: Mapped[UserRole] = mapped_column(
        # values_callable stores the member *values* ("user"), not the names
        # ("USER"), which is what SQLAlchemy would otherwise write.
        Enum(
            UserRole,
            name="user_role",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        server_default=UserRole.USER.value,
    )

    # timezone=True -> TIMESTAMPTZ, so these are unambiguous instants rather
    # than naive local times.
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        # Applied by SQLAlchemy on ORM/Core updates -- see the note in the
        # migration about writes that bypass it.
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role})>"


_BY_CLERK_ID = text("SELECT id FROM users WHERE clerk_user_id = :clerk_user_id")

# Links only a row nobody has claimed: `clerk_user_id IS NULL` is in the same
# statement as the write, so two accounts with the same address cannot both
# take it. The subquery rather than a WHERE on the UPDATE itself so that two
# rows matching case-insensitively is an error ("more than one row returned
# by a subquery") instead of both being linked -- email is unique only as
# typed.
_LINK = text(
    "UPDATE users SET clerk_user_id = :clerk_user_id "
    "WHERE id = ("
    "SELECT id FROM users "
    "WHERE lower(email) = lower(:email) AND clerk_user_id IS NULL"
    ") "
    "RETURNING id"
)


async def user_by_clerk_id(
    session: AsyncSession, clerk_user_id: str
) -> uuid.UUID | None:
    """The user a Clerk account is linked to, if it is linked yet."""
    return await session.scalar(_BY_CLERK_ID, {"clerk_user_id": clerk_user_id})


async def link_clerk_user(
    session: AsyncSession, clerk_user_id: str, email: str
) -> uuid.UUID | None:
    """Link a Clerk account to the unclaimed user with its email.

    Returns the user's id, or None when no unclaimed user has that email.
    The caller commits.
    """
    return await session.scalar(_LINK, {"clerk_user_id": clerk_user_id, "email": email})


# ON CONFLICT DO NOTHING covers both unique columns: a request racing this one
# that already created the row for this account, or an email some other row
# holds. Either way nothing is written and nothing is returned, and the caller
# tells the two apart by looking the account up again.
_CREATE = text(
    "INSERT INTO users (email, clerk_user_id) VALUES (:email, :clerk_user_id) "
    "ON CONFLICT DO NOTHING "
    "RETURNING id"
)


async def create_clerk_user(
    session: AsyncSession, clerk_user_id: str, email: str
) -> uuid.UUID | None:
    """Create the user for a Clerk account signing in for the first time.

    Returns the new user's id, or None when either the account or the email
    already has a row. The caller commits.
    """
    return await session.scalar(
        _CREATE, {"clerk_user_id": clerk_user_id, "email": email}
    )
