"""Pydantic schemas for tenant routes."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TenantResponse(BaseModel):
    id: str
    name: str
    email: str | None


class AppIntegrationResponse(BaseModel):
    id: str
    app_name: str
    config: dict[str, object] = Field(default_factory=dict)
