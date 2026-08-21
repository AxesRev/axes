"""Point the Paddle notification destination at this billing API Gateway URL.

No Paddle Terraform provider exists. Stdlib + AWS CLI so apply-apps needs no extra deps.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any

SANDBOX_API_BASE = "https://sandbox-api.paddle.com"
LIVE_API_BASE = "https://api.paddle.com"
SUBSCRIBED_EVENTS = (
    "subscription.created",
    "subscription.updated",
    "transaction.completed",
)


def webhook_url(public_url: str) -> str:
    return f"{public_url.rstrip('/')}/billing/webhooks"


def api_base(api_key: str) -> str:
    if api_key.startswith("pdl_sdbx_"):
        return SANDBOX_API_BASE
    return LIVE_API_BASE


def pick_setting(
    settings: list[dict[str, Any]],
    *,
    setting_id: str,
    description: str,
    destination: str,
) -> dict[str, Any] | None:
    if setting_id:
        match = next((item for item in settings if item.get("id") == setting_id), None)
        if match is None:
            raise RuntimeError(f"Paddle notification setting {setting_id} was not found")
        return match
    url_settings = [item for item in settings if item.get("type") == "url"]
    by_description = next((item for item in url_settings if item.get("description") == description), None)
    if by_description is not None:
        return by_description
    by_destination = next((item for item in url_settings if item.get("destination") == destination), None)
    if by_destination is not None:
        return by_destination
    by_path = next(
        (item for item in url_settings if str(item.get("destination") or "").endswith("/billing/webhooks")),
        None,
    )
    if by_path is not None:
        return by_path
    if len(url_settings) == 1:
        return url_settings[0]
    return None


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
        raise RuntimeError(f"Failed to write Paddle notification settings to {name}") from None


def _paddle_json(
    api_key: str,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        f"{api_base(api_key)}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode() or f"HTTP {exc.code}"
        raise RuntimeError(f"Paddle {method} {path} failed: {detail}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected Paddle response")
    return payload


def _list_settings(api_key: str) -> list[dict[str, Any]]:
    payload = _paddle_json(api_key, "GET", "/notification-settings")
    data = payload.get("data")
    if not isinstance(data, list):
        raise RuntimeError("Paddle notification-settings response missing data")
    return [item for item in data if isinstance(item, dict)]


def _update_lambda_secret(function_name: str, region: str, secret: str) -> None:
    raw = subprocess.check_output(
        [
            "aws",
            "lambda",
            "get-function-configuration",
            "--function-name",
            function_name,
            "--region",
            region,
            "--output",
            "json",
        ],
        text=True,
    )
    current = json.loads(raw).get("Environment", {}).get("Variables") or {}
    current["PADDLE_WEBHOOK_SECRET"] = secret
    subprocess.check_call(
        [
            "aws",
            "lambda",
            "update-function-configuration",
            "--function-name",
            function_name,
            "--region",
            region,
            "--environment",
            json.dumps({"Variables": current}),
        ],
        stdout=subprocess.DEVNULL,
    )


def deploy_notification() -> None:
    public_url = _required_env("BILLING_PUBLIC_URL")
    ssm_name = _required_env("SSM_SECRETS_PARAMETER")
    region = os.environ.get("AWS_REGION", "").strip() or os.environ.get("AWS_DEFAULT_REGION", "").strip()
    if not region:
        raise ValueError("AWS_REGION is required")
    description = os.environ.get("DESTINATION_DESCRIPTION", "").strip() or "axes-billing"
    destination = webhook_url(public_url)

    secrets = _ssm_get(ssm_name, region)
    api_key = str(secrets.get("PADDLE_API_KEY") or "").strip()
    if not api_key:
        raise ValueError("PADDLE_API_KEY is missing from SSM")

    setting_id = str(secrets.get("PADDLE_NOTIFICATION_SETTING_ID") or "").strip()
    existing = pick_setting(
        _list_settings(api_key),
        setting_id=setting_id,
        description=description,
        destination=destination,
    )
    created = False
    if existing is None:
        payload = _paddle_json(
            api_key,
            "POST",
            "/notification-settings",
            {
                "description": description,
                "type": "url",
                "destination": destination,
                "subscribed_events": list(SUBSCRIBED_EVENTS),
            },
        )
        setting = payload.get("data")
        created = True
    else:
        payload = _paddle_json(
            api_key,
            "PATCH",
            f"/notification-settings/{existing['id']}",
            {"destination": destination, "active": True},
        )
        setting = payload.get("data") or existing

    if not isinstance(setting, dict) or not setting.get("id"):
        raise RuntimeError("Paddle notification setting response missing id")

    secrets["PADDLE_NOTIFICATION_SETTING_ID"] = str(setting["id"])
    new_secret = str(setting.get("endpoint_secret_key") or "").strip()
    if created and new_secret:
        secrets["PADDLE_WEBHOOK_SECRET"] = new_secret
    _ssm_put(ssm_name, region, secrets)

    if created and new_secret:
        for name in (
            os.environ.get("LAMBDA_API_FUNCTION", "").strip(),
            os.environ.get("LAMBDA_CHARGE_FUNCTION", "").strip(),
        ):
            if name:
                _update_lambda_secret(name, region, new_secret)

    action = "created" if created else "updated"
    print(f"Paddle notification destination {action}: {setting['id']} -> {destination}", flush=True)


def main() -> None:
    try:
        deploy_notification()
    except (RuntimeError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
