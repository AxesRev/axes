"""Shared mappings for tenant-scoped Postgres tables.

Schema is owned by Alembic in langraph_server. Services import these models
and do not declare their own copies.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    auth0_sub: Mapped[str | None] = mapped_column(Text, nullable=True)


class AppIntegration(Base):
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
    extra_app_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_user_identities_slack_user_id", "slack_user_id", unique=True),
        Index("idx_user_identities_tenant_id", "tenant_id"),
    )


class TenantAgentContext(Base):
    __tablename__ = "tenant_agent_context"

    tenant_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class OAuthState(Base):
    __tablename__ = "oauth_states"

    token: Mapped[str] = mapped_column(Text, primary_key=True)
    slack_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (Index("idx_oauth_states_slack_user_id", "slack_user_id"),)
