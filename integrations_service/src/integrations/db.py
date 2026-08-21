"""Integrations SQLAlchemy session against the shared RDS."""

from common.db import Database
from integrations.config import settings

_db = Database(
    settings.database_url,
    pool_size=settings.SQLALCHEMY_POOL_SIZE,
    max_overflow=settings.SQLALCHEMY_MAX_OVERFLOW,
    echo=settings.DB_ECHO_LOG,
)

session_scope = _db.session_scope
