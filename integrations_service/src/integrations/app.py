"""API Gateway HTTP API (payload 2.0) Lambda handler for install HTTP."""

from __future__ import annotations

import asyncio
from typing import Any

from integrations.db import session_scope
from integrations.errors import HttpError
from integrations.github import github_callback, github_install, github_oauth_start
from integrations.http import json_response, method_and_path
from integrations.salesforce import (
    salesforce_complete_form,
    salesforce_complete_submit,
    salesforce_connect,
    salesforce_install,
)
from integrations.slack import slack_callback, slack_install


async def _with_session():
    return session_scope()


async def _handle(event: dict[str, Any]) -> dict[str, object]:
    method, path = method_and_path(event)
    try:
        if method == "GET" and path == "/app_integrations/slack/install":
            async with await _with_session() as session:
                return await slack_install(event, session)
        if method == "GET" and path == "/app_integrations/slack/callback":
            async with await _with_session() as session:
                return await slack_callback(event, session)

        if method == "GET" and path == "/app_integrations/github/install":
            async with await _with_session() as session:
                return await github_install(event, session)
        if method == "GET" and path == "/app_integrations/github/start":
            async with await _with_session() as session:
                return await github_oauth_start(event, session)
        if method == "GET" and path == "/app_integrations/github/callback":
            async with await _with_session() as session:
                return await github_callback(event, session)

        if method == "GET" and path == "/app_integrations/salesforce/install":
            async with await _with_session() as session:
                return await salesforce_install(event, session)
        if method == "GET" and path == "/app_integrations/salesforce/connect":
            async with await _with_session() as session:
                return await salesforce_connect(event, session)
        if method == "GET" and path == "/app_integrations/salesforce/complete":
            return salesforce_complete_form(event)
        if method == "POST" and path == "/app_integrations/salesforce/complete":
            async with await _with_session() as session:
                return await salesforce_complete_submit(event, session)
    except HttpError as error:
        return json_response(error.status_code, {"detail": error.detail})

    return json_response(404, {"detail": "Not found"})


def handler(event: dict[str, Any], _context: object) -> dict[str, object]:
    return asyncio.run(_handle(event))
