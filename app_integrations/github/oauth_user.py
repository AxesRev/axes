"""Fetch GitHub user id and email after OAuth token exchange."""

from __future__ import annotations

import re

import httpx
from fastapi import HTTPException, status

_GITHUB_USER_URL = "https://api.github.com/user"
_GITHUB_EMAILS_URL = "https://api.github.com/user/emails"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_github_email(email: str) -> str | None:
    normalized = email.strip().lower()
    if not normalized or not _EMAIL_RE.fullmatch(normalized):
        return None
    return normalized


async def fetch_github_user_id_and_email(
    client: httpx.AsyncClient,
    *,
    access_token: str,
) -> tuple[str, str]:
    """Return GitHub numeric user id and a verified email for the authorized user."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    user_response = await client.get(_GITHUB_USER_URL, headers=headers)
    if user_response.status_code != status.HTTP_200_OK:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch GitHub user information.",
        )

    user_data = user_response.json()
    github_user_id = str(user_data["id"])

    email: str | None = None
    raw_email = user_data.get("email")
    if isinstance(raw_email, str) and raw_email.strip():
        email = normalize_github_email(raw_email)

    if email is None:
        emails_response = await client.get(_GITHUB_EMAILS_URL, headers=headers)
        if emails_response.status_code != status.HTTP_200_OK:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to fetch GitHub user emails.",
            )
        email = _pick_primary_email(emails_response.json())

    if email is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "GitHub did not provide a verified email for this account. "
                "Grant the user:email scope and ensure your GitHub account has a primary email."
            ),
        )

    return github_user_id, email


def _pick_primary_email(entries: object) -> str | None:
    if not isinstance(entries, list):
        return None

    primary: str | None = None
    fallback: str | None = None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("verified") is not True:
            continue
        address = entry.get("email")
        if not isinstance(address, str):
            continue
        normalized = normalize_github_email(address)
        if normalized is None:
            continue
        if entry.get("primary") is True:
            primary = normalized
            break
        if fallback is None:
            fallback = normalized

    return primary or fallback
