"""Slack app API routes — thin wrappers around the Bolt handler."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler

from slack_app.bolt import bolt_app

router = APIRouter()
_handler = AsyncSlackRequestHandler(bolt_app)


@router.post("/slack/events")
async def slack_events(req: Request) -> Response:
    return await _handler.handle(req)


@router.get("/slack/oauth/install")
async def slack_install(req: Request) -> Response:
    return await _handler.handle(req)


@router.get("/slack/oauth/callback")
async def slack_oauth_callback(req: Request) -> Response:
    return await _handler.handle(req)


@router.get("/slack/health")
async def slack_health() -> dict[str, str]:
    return {"status": "healthy", "service": "slack_app"}
