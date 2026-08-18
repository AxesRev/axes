"""Unit tests for Slack manifest deploy."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from slack_app.deploy_manifest import _apply_server_url, deploy_manifest


@pytest.mark.unit
def test_apply_server_url_rewrites_events_commands_and_oauth() -> None:
    manifest = {
        "features": {"slash_commands": [{"command": "/axes", "url": "https://old/slack/commands"}]},
        "oauth_config": {"redirect_urls": ["https://old/app_integrations/slack/callback"]},
        "settings": {"event_subscriptions": {"request_url": "https://old/slack/events"}},
    }

    updated = _apply_server_url(
        manifest,
        "https://slack.execute-api.eu-west-1.amazonaws.com",
        "https://integrations.execute-api.eu-west-1.amazonaws.com",
    )

    assert updated["settings"]["event_subscriptions"]["request_url"] == (
        "https://slack.execute-api.eu-west-1.amazonaws.com/slack/events"
    )
    assert updated["features"]["slash_commands"][0]["url"] == (
        "https://slack.execute-api.eu-west-1.amazonaws.com/slack/commands"
    )
    assert updated["oauth_config"]["redirect_urls"] == [
        "https://integrations.execute-api.eu-west-1.amazonaws.com/app_integrations/slack/callback"
    ]
    assert updated["settings"]["org_deploy_enabled"] is True
    assert manifest["settings"]["event_subscriptions"]["request_url"] == "https://old/slack/events"


@pytest.mark.unit
def test_deploy_manifest_writes_refresh_token_before_update(tmp_path) -> None:
    manifest_path = tmp_path / "slack_manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    secrets = {
        "SLACK_APP_ID": "A0TEST",
        "SLACK_APP_CONFIG_REFRESH_TOKEN": "old-refresh",
        "OTHER": "keep",
    }
    order: list[str] = []

    def wait(_server_url: str) -> None:
        order.append("wait")

    def rotate(_refresh: str) -> tuple[str, str]:
        order.append("rotate")
        return "access-token", "new-refresh"

    def put(_name: str, _region: str, values: dict) -> None:
        order.append("put")
        secrets.clear()
        secrets.update(values)

    def update(_access: str, _app_id: str, _manifest: dict) -> None:
        order.append("update")

    env = {
        "SERVER_URL": "https://slack.example",
        "INTEGRATIONS_PUBLIC_URL": "https://integrations.example",
        "SSM_SECRETS_PARAMETER": "/axes/dev/secrets",
        "AWS_REGION": "eu-west-1",
        "MANIFEST_PATH": str(manifest_path),
    }

    with (
        patch.dict("os.environ", env, clear=False),
        patch("slack_app.deploy_manifest._ssm_get", return_value=dict(secrets)),
        patch("slack_app.deploy_manifest._ssm_put", side_effect=put),
        patch("slack_app.deploy_manifest._rotate_config_token", side_effect=rotate),
        patch("slack_app.deploy_manifest._wait_ready", side_effect=wait),
        patch("slack_app.deploy_manifest._update_manifest", side_effect=update),
    ):
        deploy_manifest()

    assert order == ["wait", "rotate", "put", "update"]
    assert secrets["SLACK_APP_CONFIG_REFRESH_TOKEN"] == "new-refresh"
    assert secrets["OTHER"] == "keep"
    assert "SLACK_APP_CONFIG_TOKEN" not in secrets


@pytest.mark.unit
def test_update_manifest_sends_manifest_as_json_string() -> None:
    captured: dict[str, bytes] = {}

    def fake_http(_url: str, data: bytes, _headers: dict[str, str]) -> dict:
        captured["data"] = data
        return {"ok": True}

    with patch("slack_app.deploy_manifest._http_json", side_effect=fake_http):
        from slack_app.deploy_manifest import _update_manifest

        _update_manifest("token", "A0TEST", {"display_information": {"name": "Axes"}})

    payload = json.loads(captured["data"].decode())
    assert payload["app_id"] == "A0TEST"
    assert isinstance(payload["manifest"], str)
    assert json.loads(payload["manifest"]) == {"display_information": {"name": "Axes"}}


@pytest.mark.unit
def test_update_manifest_includes_schema_errors() -> None:
    def fake_http(_url: str, _data: bytes, _headers: dict[str, str]) -> dict:
        return {
            "ok": False,
            "error": "invalid_manifest",
            "errors": [{"message": "bad field", "pointer": "/settings"}],
        }

    with patch("slack_app.deploy_manifest._http_json", side_effect=fake_http):
        from slack_app.deploy_manifest import _update_manifest

        with pytest.raises(RuntimeError, match="invalid_manifest.*bad field"):
            _update_manifest("token", "A0TEST", {})
