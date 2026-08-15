"""Read/write mappings for existing Postgres tables. Billing does not own schema."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import TIMESTAMP, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    auth0_sub: Mapped[str | None] = mapped_column(Text, nullable=True)
    paddle_customer_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    paddle_subscription_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    paddle_subscription_status: Mapped[str | None] = mapped_column(Text, nullable=True)


class UserIdentity(Base):
    __tablename__ = "user_identities"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    slack_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)


class Run(Base):
    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    token_usage: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
