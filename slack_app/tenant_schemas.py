"""Pydantic schemas for tenant routes."""

from __future__ import annotations

from pydantic import BaseModel


class TenantResponse(BaseModel):
    id: str
    name: str
    email: str | None
