"""Read/write mappings for existing Postgres tables. Slack app does not own schema."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AppIntegration(Base):
    __tablename__ = "app_integrations"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    app_name: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)


class UserIdentity(Base):
    __tablename__ = "user_identities"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    slack_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    extra_app_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class OAuthState(Base):
    __tablename__ = "oauth_states"

    token: Mapped[str] = mapped_column(Text, primary_key=True)
    slack_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
