"""Pydantic request/response schemas.

Deliberately separate from ``model``: that package is the ORM layer whose
``__init__`` feeds ``Base.metadata`` to Alembic autogenerate. Wire formats
and table definitions change for different reasons, so they stay apart.
"""

from schema.message import MessageRequest

__all__ = ["MessageRequest"]
