"""ORM models.

Import every model here. Alembic's autogenerate only sees tables already
registered on ``Base.metadata``, so a model that is never imported is
silently invisible -- and autogenerate will emit a migration dropping its
table. Importing them here means ``import model`` is enough.
"""

from database.database import Base
from model.user import User, UserRole

__all__ = ["Base", "User", "UserRole"]
