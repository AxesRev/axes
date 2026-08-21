"""Unit tests for Paddle notification destination deploy."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from billing.deploy_notification import api_base, pick_setting, webhook_url


@pytest.mark.unit
def test_webhook_url_appends_billing_path() -> None:
    assert webhook_url("https://abc.execute-api.eu-west-1.amazonaws.com") == (
        "https://abc.execute-api.eu-west-1.amazonaws.com/billing/webhooks"
    )


@pytest.mark.unit
def test_api_base_uses_sandbox_for_sandbox_keys() -> None:
    assert api_base("pdl_sdbx_apikey_test") == "https://sandbox-api.paddle.com"
    assert api_base("pdl_live_apikey_test") == "https://api.paddle.com"


@pytest.mark.unit
def test_pick_setting_prefers_stored_id() -> None:
    settings = [
        {
            "id": "ntfset_other",
            "type": "url",
            "description": "axes-billing",
            "destination": "https://old/billing/webhooks",
        },
        {"id": "ntfset_kept", "type": "url", "description": "other", "destination": "https://x"},
    ]
    picked = pick_setting(
        settings,
        setting_id="ntfset_kept",
        description="axes-billing",
        destination="https://new/billing/webhooks",
    )
    assert picked is not None
    assert picked["id"] == "ntfset_kept"


@pytest.mark.unit
def test_pick_setting_matches_description_then_destination() -> None:
    settings = [
        {"id": "ntfset_desc", "type": "url", "description": "axes-billing", "destination": "https://old"},
        {"id": "ntfset_url", "type": "url", "description": "misc", "destination": "https://new/billing/webhooks"},
    ]
    by_desc = pick_setting(
        settings, setting_id="", description="axes-billing", destination="https://new/billing/webhooks"
    )
    assert by_desc is not None and by_desc["id"] == "ntfset_desc"

    by_url = pick_setting(settings, setting_id="", description="missing", destination="https://new/billing/webhooks")
    assert by_url is not None and by_url["id"] == "ntfset_url"


@pytest.mark.unit
def test_pick_setting_uses_sole_url_destination() -> None:
    settings = [
        {"id": "ntfset_email", "type": "email", "description": "ops", "destination": "ops@example.com"},
        {"id": "ntfset_only", "type": "url", "description": "legacy", "destination": "https://old.example/hook"},
    ]
    picked = pick_setting(
        settings, setting_id="", description="dev-billing", destination="https://new/billing/webhooks"
    )
    assert picked is not None and picked["id"] == "ntfset_only"


@pytest.mark.unit
def test_deploy_notification_patches_existing_destination() -> None:
    secrets = {"PADDLE_API_KEY": "pdl_sdbx_apikey_test", "PADDLE_NOTIFICATION_SETTING_ID": "ntfset_1"}
    calls: list[tuple[str, str]] = []

    def fake_paddle(_api_key: str, method: str, path: str, body: dict | None = None) -> dict:
        calls.append((method, path))
        if method == "GET":
            return {
                "data": [
                    {
                        "id": "ntfset_1",
                        "type": "url",
                        "description": "dev-billing",
                        "destination": "https://old/billing/webhooks",
                    }
                ]
            }
        return {"data": {"id": "ntfset_1", "destination": body["destination"] if body else ""}}

    env = {
        "BILLING_PUBLIC_URL": "https://abc.execute-api.eu-west-1.amazonaws.com",
        "SSM_SECRETS_PARAMETER": "/axes/dev/secrets",
        "AWS_REGION": "eu-west-1",
        "DESTINATION_DESCRIPTION": "dev-billing",
    }
    with (
        patch.dict("os.environ", env, clear=False),
        patch("billing.deploy_notification._ssm_get", return_value=secrets),
        patch("billing.deploy_notification._ssm_put") as put,
        patch("billing.deploy_notification._paddle_json", side_effect=fake_paddle),
        patch("billing.deploy_notification._update_lambda_secret") as update_lambda,
    ):
        from billing.deploy_notification import deploy_notification

        deploy_notification()

    assert ("PATCH", "/notification-settings/ntfset_1") in calls
    put.assert_called_once()
    update_lambda.assert_not_called()


@pytest.mark.unit
def test_deploy_notification_creates_when_none_exist() -> None:
    secrets = {"PADDLE_API_KEY": "pdl_sdbx_apikey_test"}

    def fake_paddle(_api_key: str, method: str, path: str, body: dict | None = None) -> dict:
        if method == "GET":
            return {"data": []}
        assert method == "POST"
        assert body is not None
        assert body["destination"].endswith("/billing/webhooks")
        return {
            "data": {
                "id": "ntfset_new",
                "destination": body["destination"],
                "endpoint_secret_key": "pdl_ntfset_secret",
            }
        }

    env = {
        "BILLING_PUBLIC_URL": "https://abc.execute-api.eu-west-1.amazonaws.com",
        "SSM_SECRETS_PARAMETER": "/axes/dev/secrets",
        "AWS_REGION": "eu-west-1",
        "DESTINATION_DESCRIPTION": "dev-billing",
        "LAMBDA_API_FUNCTION": "dev-billing-api",
        "LAMBDA_CHARGE_FUNCTION": "dev-billing-charge",
    }
    with (
        patch.dict("os.environ", env, clear=False),
        patch("billing.deploy_notification._ssm_get", return_value=secrets),
        patch("billing.deploy_notification._ssm_put") as put,
        patch("billing.deploy_notification._paddle_json", side_effect=fake_paddle),
        patch("billing.deploy_notification._update_lambda_secret") as update_lambda,
    ):
        from billing.deploy_notification import deploy_notification

        deploy_notification()

    written = put.call_args.args[2]
    assert written["PADDLE_NOTIFICATION_SETTING_ID"] == "ntfset_new"
    assert written["PADDLE_WEBHOOK_SECRET"] == "pdl_ntfset_secret"
    assert update_lambda.call_count == 2
