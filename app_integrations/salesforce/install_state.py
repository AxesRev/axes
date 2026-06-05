"""Signed state for Salesforce package install return URLs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt as pyjwt

_INSTALL_STATE_TTL_SECONDS = 600


def create_salesforce_install_state(*, tenant_id: str, secret: str) -> str:
    """Return a JWT tying the post-install step to a tenant."""
    return pyjwt.encode(
        {
            "tenant_id": tenant_id,
            "exp": datetime.now(UTC) + timedelta(seconds=_INSTALL_STATE_TTL_SECONDS),
        },
        secret,
        algorithm="HS256",
    )


def decode_salesforce_install_state(state: str, secret: str) -> str:
    """Validate install state JWT and return tenant_id."""
    claims = pyjwt.decode(
        state,
        secret,
        algorithms=["HS256"],
        options={"require": ["tenant_id", "exp"]},
    )
    tenant_id = claims["tenant_id"]
    if not isinstance(tenant_id, str) or not tenant_id:
        raise ValueError("state is missing tenant_id")
    return tenant_id
