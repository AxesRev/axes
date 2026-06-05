"""Unit tests for Paddle webhook signature verification."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

from billing.webhooks import WebhookVerificationError, verify_paddle_webhook_signature


def _signed_header(*, body: bytes, secret: str, timestamp: int | None = None) -> str:
    event_time = timestamp if timestamp is not None else int(time.time())
    signed_payload = f"{event_time}:".encode() + body
    signature = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"ts={event_time};h1={signature}"


@pytest.mark.unit
def test_verify_paddle_webhook_signature_accepts_valid_signature() -> None:
    body = json.dumps({"event_type": "subscription.created", "data": {}}).encode()
    secret = "whsec_test_secret"

    verify_paddle_webhook_signature(
        raw_body=body,
        signature_header=_signed_header(body=body, secret=secret),
        secret_key=secret,
    )


@pytest.mark.unit
def test_verify_paddle_webhook_signature_rejects_missing_header() -> None:
    with pytest.raises(WebhookVerificationError, match="missing"):
        verify_paddle_webhook_signature(raw_body=b"{}", signature_header=None, secret_key="secret")


@pytest.mark.unit
def test_verify_paddle_webhook_signature_rejects_invalid_signature() -> None:
    body = b'{"event_type":"subscription.created"}'
    timestamp = int(time.time())
    with pytest.raises(WebhookVerificationError, match="does not match"):
        verify_paddle_webhook_signature(
            raw_body=body,
            signature_header=f"ts={timestamp};h1=deadbeef",
            secret_key="secret",
        )


@pytest.mark.unit
def test_verify_paddle_webhook_signature_rejects_stale_event() -> None:
    body = b'{"event_type":"subscription.created"}'
    secret = "whsec_test_secret"
    stale_timestamp = int(time.time()) - 600

    with pytest.raises(WebhookVerificationError, match="too old"):
        verify_paddle_webhook_signature(
            raw_body=body,
            signature_header=_signed_header(body=body, secret=secret, timestamp=stale_timestamp),
            secret_key=secret,
        )
