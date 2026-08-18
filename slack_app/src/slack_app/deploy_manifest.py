"""Push slack_manifest.json after the Bolt pod answers through API Gateway.

Wait for public GET /health (routes + NLB + pod). Then rotate the Slack config
token, write the new refresh token to SSM, and call apps.manifest.update.
Stdlib + AWS CLI so apply-apps needs no extra Python deps.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy
from pathlib import Path
from typing import Any

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "slack_manifest.json"
SLACK_API_BASE = "https://slack.com/api"
ROTATE_PATH = "/tooling.tokens.rotate"
UPDATE_PATH = "/apps.manifest.update"
HEALTH_ATTEMPTS = 60
HEALTH_WAIT_SECONDS = 5
UPDATE_ATTEMPTS = 8
UPDATE_WAIT_SECONDS = 5
FATAL_SLACK_ERRORS = frozenset(
    {
        "invalid_auth",
        "invalid_refresh_token",
        "token_expired",
        "not_allowed",
        "app_not_found",
        "account_inactive",
    }
)


def _apply_server_url(
    manifest: dict[str, Any],
    server_url: str,
    oauth_url: str,
) -> dict[str, Any]:
    """Replace placeholder URLs with Slack events host and integrations OAuth host."""
    server_url = server_url.rstrip("/")
    oauth_url = oauth_url.rstrip("/")
    updated = deepcopy(manifest)

    oauth_config = updated.setdefault("oauth_config", {})
    oauth_config["redirect_urls"] = [f"{oauth_url}/app_integrations/slack/callback"]

    for command in updated.get("features", {}).get("slash_commands", []):
        command["url"] = f"{server_url}/slack/commands"

    event_subscriptions = updated.setdefault("settings", {}).setdefault("event_subscriptions", {})
    event_subscriptions["request_url"] = f"{server_url}/slack/events"

    return updated


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _ssm_get(name: str, region: str) -> dict[str, Any]:
    raw = subprocess.check_output(
        [
            "aws",
            "ssm",
            "get-parameter",
            "--name",
            name,
            "--with-decryption",
            "--region",
            region,
            "--output",
            "json",
        ],
        text=True,
    )
    value = json.loads(json.loads(raw)["Parameter"]["Value"])
    if not isinstance(value, dict):
        raise RuntimeError(f"SSM parameter {name} is not a JSON object")
    return value


def _ssm_put(name: str, region: str, values: dict[str, Any]) -> None:
    try:
        subprocess.check_call(
            [
                "aws",
                "ssm",
                "put-parameter",
                "--name",
                name,
                "--type",
                "SecureString",
                "--tier",
                "Advanced",
                "--value",
                json.dumps(values, separators=(",", ":")),
                "--overwrite",
                "--region",
                region,
            ],
            stdout=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        raise RuntimeError(f"Failed to write refresh token to {name}") from None


def _http_json(url: str, data: bytes, headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        payload = json.loads(exc.read().decode() or "{}")
        if not payload:
            raise RuntimeError(f"HTTP {exc.code} from {url}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected Slack response from {url}")
    return payload


def _rotate_config_token(refresh_token: str) -> tuple[str, str]:
    payload = _http_json(
        f"{SLACK_API_BASE}{ROTATE_PATH}",
        urllib.parse.urlencode({"refresh_token": refresh_token}).encode(),
        {"Content-Type": "application/x-www-form-urlencoded"},
    )
    if not payload.get("ok"):
        raise RuntimeError(f"tooling.tokens.rotate failed: {payload.get('error', 'unknown_error')}")
    access = str(payload.get("token") or "").strip()
    new_refresh = str(payload.get("refresh_token") or "").strip()
    if not access or not new_refresh:
        raise RuntimeError("tooling.tokens.rotate returned empty token")
    return access, new_refresh


def _wait_ready(server_url: str) -> None:
    """Block until API Gateway reaches the live Bolt pod (404/502 keep waiting)."""
    url = f"{server_url.rstrip('/')}/health"
    last_error: Exception | None = None
    for attempt in range(1, HEALTH_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(url, timeout=5) as response:  # nosec B310
                if 200 <= response.status < 300:
                    print(f"Slack Bolt ready at {url}", flush=True)
                    return
        except Exception as exc:  # noqa: BLE001 — poll until timeout
            last_error = exc
            print(f"Waiting for Slack Bolt ({attempt}/{HEALTH_ATTEMPTS}): {exc}", flush=True)
        time.sleep(HEALTH_WAIT_SECONDS)
    raise RuntimeError(f"Slack Bolt not reachable at {url}: {last_error}")


def _update_manifest(access_token: str, app_id: str, manifest: dict[str, Any]) -> None:
    last_error = "unknown_error"
    for attempt in range(UPDATE_ATTEMPTS):
        payload = _http_json(
            f"{SLACK_API_BASE}{UPDATE_PATH}",
            json.dumps({"app_id": app_id, "manifest": manifest}).encode(),
            {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
        )
        if payload.get("ok"):
            return
        last_error = str(payload.get("error", "unknown_error"))
        if last_error in FATAL_SLACK_ERRORS:
            raise RuntimeError(f"apps.manifest.update failed: {last_error}")
        if attempt < UPDATE_ATTEMPTS - 1:
            time.sleep(UPDATE_WAIT_SECONDS)
    raise RuntimeError(f"apps.manifest.update failed: {last_error}")


def deploy_manifest() -> None:
    server_url = _required_env("SERVER_URL")
    oauth_url = os.environ.get("INTEGRATIONS_PUBLIC_URL", "").strip() or server_url
    ssm_name = _required_env("SSM_SECRETS_PARAMETER")
    region = os.environ.get("AWS_REGION", "").strip() or os.environ.get("AWS_DEFAULT_REGION", "").strip()
    if not region:
        raise ValueError("AWS_REGION is required")

    manifest_path = Path(os.environ.get("MANIFEST_PATH", "").strip() or MANIFEST_PATH)
    secrets = _ssm_get(ssm_name, region)
    app_id = str(secrets.get("SLACK_APP_ID") or "").strip()
    refresh_token = str(secrets.get("SLACK_APP_CONFIG_REFRESH_TOKEN") or "").strip()
    if not app_id:
        raise ValueError("SLACK_APP_ID is missing from SSM")
    if not refresh_token:
        raise ValueError("SLACK_APP_CONFIG_REFRESH_TOKEN is missing from SSM")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = _apply_server_url(manifest, server_url, oauth_url)
    _wait_ready(server_url)

    access_token, new_refresh = _rotate_config_token(refresh_token)
    secrets["SLACK_APP_CONFIG_REFRESH_TOKEN"] = new_refresh
    secrets.pop("SLACK_APP_CONFIG_TOKEN", None)
    _ssm_put(ssm_name, region, secrets)
    _update_manifest(access_token, app_id, manifest)
    print(f"Slack manifest updated for app_id={app_id}")


def main() -> None:
    try:
        deploy_manifest()
    except (RuntimeError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
