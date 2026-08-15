"""Tenant SQLAlchemy session against the shared RDS."""

from common.db import Database
from tenants.config import tenant_settings

_db = Database(
    tenant_settings.database_url,
    pool_size=tenant_settings.SQLALCHEMY_POOL_SIZE,
    max_overflow=tenant_settings.SQLALCHEMY_MAX_OVERFLOW,
    echo=tenant_settings.DB_ECHO_LOG,
)

session_scope = _db.session_scope
