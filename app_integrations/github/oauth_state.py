"""Signing and verification of the GitHub OAuth ``state`` parameter.

The state is a dot-separated string:

    <base64url(json_payload)>.<hmac_hex_signature>

The payload contains:
    - ``slack_user_id``: the Slack user initiating the flow
    - ``nonce``: a random hex string preventing replay attacks
    - ``exp``: Unix timestamp after which the state is invalid

The HMAC key is ``GITHUB_OAUTH_STATE_SECRET`` from settings.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

_ENCODING = "utf-8"


def _b64_encode(data: dict[str, object]) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode(_ENCODING)
    return base64.urlsafe_b64encode(raw).decode(_ENCODING).rstrip("=")


def _b64_decode(s: str) -> dict[str, object]:
    padding = (4 - len(s) % 4) % 4
    raw = base64.urlsafe_b64decode(s + "=" * padding)
    return json.loads(raw.decode(_ENCODING))


def _sign(encoded_payload: str, secret: str) -> str:
    return hmac.new(
        secret.encode(_ENCODING),
        encoded_payload.encode(_ENCODING),
        hashlib.sha256,
    ).hexdigest()


def create_github_oauth_state(slack_user_id: str, secret: str, ttl_seconds: int = 300) -> str:
    """Create a signed, time-limited OAuth state string."""
    payload = {
        "slack_user_id": slack_user_id,
        "nonce": secrets.token_hex(16),
        "exp": int(time.time()) + ttl_seconds,
    }
    encoded = _b64_encode(payload)
    signature = _sign(encoded, secret)
    return f"{encoded}.{signature}"


def verify_github_oauth_state(state: str, secret: str) -> str:
    """Verify a signed OAuth state and return the embedded ``slack_user_id``."""
    try:
        encoded, signature = state.rsplit(".", 1)
    except ValueError as exc:
        raise ValueError("Malformed OAuth state: missing signature segment") from exc

    expected_sig = _sign(encoded, secret)
    if not hmac.compare_digest(signature, expected_sig):
        raise ValueError("OAuth state signature is invalid")

    try:
        payload = _b64_decode(encoded)
    except Exception as exc:
        raise ValueError("OAuth state payload could not be decoded") from exc

    if payload.get("exp", 0) < int(time.time()):
        raise ValueError("OAuth state has expired")

    slack_user_id = payload.get("slack_user_id")
    if not slack_user_id or not isinstance(slack_user_id, str):
        raise ValueError("OAuth state payload is missing slack_user_id")

    return slack_user_id
