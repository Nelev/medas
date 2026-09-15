"""ORM models.

Every model must subclass ``Base`` and live in (or be imported into) this
module, since Alembic's autogenerate only sees what ``Base.metadata`` knows
about.

Once pgvector is installed, embedding columns look like::

    from pgvector.sqlalchemy import Vector

    class Chunk(Base):
        __tablename__ = "chunk"

        id: Mapped[int] = mapped_column(primary_key=True)
        content: Mapped[str]
        embedding: Mapped[list[float]] = mapped_column(Vector(1536))
"""

import datetime
import enum
import uuid

from sqlalchemy import DateTime, Enum, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

__all__ = ["Base", "User", "UserRole"]


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
