"""Pydantic schemas for tenant routes."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from tenant.agent_context_service import AGENT_CONTEXT_MAX_LENGTH


class TenantResponse(BaseModel):
    id: str
    name: str
    email: str | None


class AppIntegrationResponse(BaseModel):
    id: str
    app_name: str
    config: dict[str, object] = Field(default_factory=dict)


class AgentContextResponse(BaseModel):
    content: str
    updated_at: datetime | None = None


class AgentContextUpdateRequest(BaseModel):
    content: str = Field(max_length=AGENT_CONTEXT_MAX_LENGTH)
