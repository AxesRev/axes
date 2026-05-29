"""SQLAlchemy ORM models for GitHub identity linking.

Registers with the shared Base from aegra_api.core.orm so that Alembic can
discover them when env.py imports this module.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegra_api.core.orm import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(Text, nullable=False)


class AppIntegration(Base):
    """Tenant-scoped integration configuration."""

    __tablename__ = "app_integrations"

    id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
        server_default=text("public.uuid_generate_v4()::text"),
    )
    tenant_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    app_name: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)

    __table_args__ = (Index("idx_app_integrations_tenant_id", "tenant_id"),)


class UserIdentity(Base):
    """Slack user belonging to a tenant."""

    __tablename__ = "user_identities"

    id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    slack_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    tenant_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_user_identities_slack_user_id", "slack_user_id", unique=True),
        Index("idx_user_identities_tenant_id", "tenant_id"),
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
