"""Paddle webhook signature verification."""

from __future__ import annotations

import hashlib
import hmac
import time


class WebhookVerificationError(Exception):
    """Raised when a Paddle webhook fails signature verification."""


def verify_paddle_webhook_signature(
    *,
    raw_body: bytes,
    signature_header: str | None,
    secret_key: str,
    max_age_seconds: int = 300,
) -> None:
    if not signature_header:
        raise WebhookVerificationError("Paddle-Signature header is missing")

    secret = secret_key.strip()
    if not secret:
        raise WebhookVerificationError("Paddle webhook secret is not configured")

    timestamp: str | None = None
    signature: str | None = None
    for part in signature_header.split(";"):
        key, _, value = part.partition("=")
        if key == "ts":
            timestamp = value
        elif key == "h1":
            signature = value

    if not timestamp or not signature:
        raise WebhookVerificationError("Paddle-Signature header is malformed")

    try:
        event_time = int(timestamp)
    except ValueError as error:
        raise WebhookVerificationError("Paddle-Signature timestamp is invalid") from error

    if abs(int(time.time()) - event_time) > max_age_seconds:
        raise WebhookVerificationError("Paddle webhook event is too old")

    signed_payload = f"{timestamp}:".encode() + raw_body
    computed = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, signature):
        raise WebhookVerificationError("Paddle webhook signature does not match")
