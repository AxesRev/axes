"""HTTP client from billing to tenant (resolve Auth0 user → tenant id)."""

from __future__ import annotations

import httpx

from billing.config import billing_settings


class TenantRef:
    def __init__(self, *, id: str, name: str, email: str | None) -> None:
        self.id = id
        self.name = name
        self.email = email


async def resolve_tenant_for_auth_user(
    *,
    auth0_sub: str,
    email: str | None,
    name: str | None,
) -> TenantRef:
    base = billing_settings.TENANT_API_URL.rstrip("/")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base}/internal/tenants/resolve",
            headers={"X-Internal-Secret": billing_settings.INTERNAL_API_SECRET},
            json={"auth0_sub": auth0_sub, "email": email, "name": name},
        )
    if response.status_code == 401:
        raise PermissionError("tenant internal auth failed")
    response.raise_for_status()
    payload = response.json()
    return TenantRef(id=payload["id"], name=payload["name"], email=payload.get("email"))
