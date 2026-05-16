"""SQLAlchemy ORM models for GitHub identity linking.

Registers with the shared Base from aegra_api.core.orm so that Alembic can
discover them when env.py imports this module.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from aegra_api.core.orm import Base


class UserIdentity(Base):
    """Identity row that can be seeded from a GitHub App install, a Slack OAuth
    link, or both.  Either source may arrive first; the other is filled in later.
    """

    __tablename__ = "user_identities"

    id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    slack_user_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_user_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_username: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_installation_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
    )

    __table_args__ = (
        # Postgres allows multiple NULLs in a unique index, so these constraints
        # only enforce uniqueness among non-null values.
        Index("idx_user_identities_slack_user_id", "slack_user_id", unique=True),
        Index("idx_user_identities_github_user_id", "github_user_id", unique=True),
        Index("idx_user_identities_github_installation_id", "github_installation_id", unique=True),
    )


class OAuthState(Base):
    """Short-lived token sent to the Slack user so they can start the OAuth flow.

    The token is a cryptographically random URL-safe string.  It is single-use
    and expires after a configurable TTL (default 5 minutes).
    """

    __tablename__ = "oauth_states"

    token: Mapped[str] = mapped_column(Text, primary_key=True)
    slack_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (Index("idx_oauth_states_slack_user_id", "slack_user_id"),)
