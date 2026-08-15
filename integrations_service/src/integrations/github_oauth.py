"""GitHub OAuth state HMAC and user profile fetch."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time

import httpx

from integrations.errors import HttpError

_ENCODING = "utf-8"
_GITHUB_USER_URL = "https://api.github.com/user"
_GITHUB_EMAILS_URL = "https://api.github.com/user/emails"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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
    payload = {
        "slack_user_id": slack_user_id,
        "nonce": secrets.token_hex(16),
        "exp": int(time.time()) + ttl_seconds,
    }
    encoded = _b64_encode(payload)
    return f"{encoded}.{_sign(encoded, secret)}"


def verify_github_oauth_state(state: str, secret: str) -> str:
    try:
        encoded, signature = state.rsplit(".", 1)
    except ValueError as exc:
        raise ValueError("Malformed OAuth state: missing signature segment") from exc

    if not hmac.compare_digest(signature, _sign(encoded, secret)):
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


def normalize_github_email(email: str) -> str | None:
    normalized = email.strip().lower()
    if not normalized or not _EMAIL_RE.fullmatch(normalized):
        return None
    return normalized


def _pick_primary_email(entries: object) -> str | None:
    if not isinstance(entries, list):
        return None
    primary: str | None = None
    fallback: str | None = None
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("verified") is not True:
            continue
        address = entry.get("email")
        if not isinstance(address, str):
            continue
        normalized = normalize_github_email(address)
        if normalized is None:
            continue
        if entry.get("primary") is True:
            return normalized
        if fallback is None:
            fallback = normalized
    return primary or fallback


async def fetch_github_user_id_and_email(client: httpx.AsyncClient, *, access_token: str) -> tuple[str, str]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    user_response = await client.get(_GITHUB_USER_URL, headers=headers)
    if user_response.status_code != 200:
        raise HttpError(502, "Failed to fetch GitHub user information.")

    user_data = user_response.json()
    github_user_id = str(user_data["id"])

    email: str | None = None
    raw_email = user_data.get("email")
    if isinstance(raw_email, str) and raw_email.strip():
        email = normalize_github_email(raw_email)

    if email is None:
        emails_response = await client.get(_GITHUB_EMAILS_URL, headers=headers)
        if emails_response.status_code != 200:
            raise HttpError(502, "Failed to fetch GitHub user emails.")
        email = _pick_primary_email(emails_response.json())

    if email is None:
        raise HttpError(
            400,
            "GitHub did not provide a verified email for this account. "
            "Grant the user:email scope and ensure your GitHub account has a primary email.",
        )
    return github_user_id, email
