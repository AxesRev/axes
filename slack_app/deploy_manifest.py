"""Update the Slack app manifest via apps.manifest.update."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx

from slack_app.config import slack_settings

MANIFEST_PATH = Path(__file__).parent / "slack_manifest.json"
SLACK_API_BASE = "https://slack.com/api"


def _apply_server_url(manifest: dict[str, Any]) -> dict[str, Any]:
    """Replace manifest placeholder URLs with SERVER_URL from settings."""
    server_url = slack_settings.SERVER_URL.rstrip("/")
    updated = deepcopy(manifest)

    oauth_config = updated.setdefault("oauth_config", {})
    oauth_config["redirect_urls"] = [f"{server_url}/slack/oauth/callback"]

    slash_commands = updated.get("features", {}).get("slash_commands", [])
    for command in slash_commands:
        command["url"] = f"{server_url}/slack/commands"

    event_subscriptions = updated.setdefault("settings", {}).setdefault("event_subscriptions", {})
    event_subscriptions["request_url"] = f"{server_url}/slack/events"

    return updated


async def deploy_manifest() -> None:
    app_id = slack_settings.SLACK_APP_ID.strip()
    config_token = slack_settings.SLACK_APP_CONFIG_TOKEN.strip()
    if not app_id:
        raise ValueError("SLACK_APP_ID is required")
    if not config_token:
        raise ValueError("SLACK_APP_CONFIG_TOKEN is required")

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest = _apply_server_url(manifest)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SLACK_API_BASE}/apps.manifest.update",
            headers={
                "Authorization": f"Bearer {config_token}",
                "Content-Type": "application/json",
            },
            json={"app_id": app_id, "manifest": manifest},
        )
        data = response.json()

    if not data.get("ok"):
        error = data.get("error", "unknown_error")
        raise RuntimeError(f"apps.manifest.update failed: {error}")

    print(f"Slack manifest updated for app_id={app_id}")


def main() -> None:
    import asyncio

    try:
        asyncio.run(deploy_manifest())
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
