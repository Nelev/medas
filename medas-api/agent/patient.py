"""The <patient> block the prompt expects, built for a real user.

Two sources, because the identity is split across them: `users` says who may
ask, and the medical record says who they are. They are joined by construction
-- the record's id is "pat_" followed by the user's uuid -- which is a
convention rather than a foreign key, so it is checked here rather than
assumed.
"""

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["UnknownPatient", "patient_block", "record_block", "record_id"]

RECORD_PATH = (
    Path(__file__).resolve().parent.parent / "rag_pipeline" / "medical_history.json"
)


class UnknownPatient(LookupError):
    """No user with that id, or no record belonging to them."""


@lru_cache
def _record() -> dict[str, Any]:
    """The patient record, read once.

    One record for now. When there are several this becomes a lookup by id,
    and the rest of this module does not change.
    """
    return json.loads(RECORD_PATH.read_text(encoding="utf-8"))


def record_id(user_id: uuid.UUID | str) -> str:
    """The record id belonging to a user."""
    return f"pat_{user_id}"


async def patient_block(session: AsyncSession, user_id: uuid.UUID | str) -> str:
    """Identity and demographics for the prompt's <patient> block.

    Raises UnknownPatient if the user does not exist, or if the record found
    does not belong to them -- handing one patient's demographics to another
    patient's conversation is the failure worth being loud about.
    """
    known = await session.scalar(
        text("SELECT id FROM users WHERE id = :user_id"), {"user_id": user_id}
    )

    if known is None:
        raise UnknownPatient(f"no user {user_id}")

    if _record().get("id") != record_id(known):
        raise UnknownPatient(f"no record for user {known}")

    return record_block()


def record_block() -> str:
    """The <patient> block itself, with no check that it is yours to see.

    Split out of patient_block so a caller that has already established whose
    record this is -- or that serves one patient and so has nothing to
    establish -- can build the block without a database round trip. The check
    stays in patient_block, which is what to reach for when the caller is
    acting on a user id it was handed.
    """
    record = _record()

    # Name, date of birth and sex: what the prompt asks for, and no more. The
    # email is in `users` and has no clinical use, so it is not sent.
    return "\n".join(
        [
            f"name: {record['name']}",
            f"date of birth: {record['dob']}",
            f"sex: {record['sex']}",
            f"record id: {record['id']}",
        ]
    )
