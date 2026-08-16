"""Slack SQLAlchemy session against the shared RDS."""

from common.db import Database
from slack_app.config import slack_settings

_db = Database(
    slack_settings.database_url,
    pool_size=slack_settings.SQLALCHEMY_POOL_SIZE,
    max_overflow=slack_settings.SQLALCHEMY_MAX_OVERFLOW,
    echo=slack_settings.DB_ECHO_LOG,
)

session_scope = _db.session_scope
