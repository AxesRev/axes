"""SQLAlchemy ORM models for GitHub OAuth linking."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import TIMESTAMP, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from aegra_api.core.orm import Base


class OAuthState(Base):
    """Short-lived token sent to a Slack user to start GitHub OAuth linking."""

    __tablename__ = "oauth_states"

    token: Mapped[str] = mapped_column(Text, primary_key=True)
    slack_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (Index("idx_oauth_states_slack_user_id", "slack_user_id"),)
