"""Billing SQLAlchemy session against the shared RDS."""

from billing.config import billing_settings
from common.db import Database

_db = Database(
    billing_settings.database_url,
    pool_size=billing_settings.SQLALCHEMY_POOL_SIZE,
    max_overflow=billing_settings.SQLALCHEMY_MAX_OVERFLOW,
    echo=billing_settings.DB_ECHO_LOG,
)

session_scope = _db.session_scope
close_engine = _db.close
