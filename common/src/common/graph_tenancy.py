"""Per-tenant ArcadeDB naming and credentials shared by ingestion and the agent.

Each tenant's graph lives in its own ArcadeDB database. Ingestion writes it as root;
the agent reads it as that tenant's read-only user, so ArcadeDB itself refuses any
query (fixed or LLM-written) that reaches another tenant's database or tries to write.

The reader password is derived from ``ARCADEDB_TENANT_KEY`` so both services agree on it
without storing per-tenant secrets. The agent never needs the root password.
"""

from __future__ import annotations

import hashlib
import hmac
import re

_NON_ALNUM = re.compile(r"[^0-9a-z]")


def tenant_database(tenant_id: str) -> str:
    """ArcadeDB database name for a tenant (``tenant_<id without separators>``)."""
    slug = _NON_ALNUM.sub("", tenant_id.strip().lower())
    if not slug:
        raise ValueError("tenant_id is required")
    return f"tenant_{slug}"


def tenant_reader_user(tenant_id: str) -> str:
    """Read-only ArcadeDB user that may only access the tenant's database."""
    return f"{tenant_database(tenant_id)}_reader"


def tenant_reader_password(tenant_id: str, tenant_key: str) -> str:
    """Deterministic reader password: HMAC-SHA256(tenant_key, tenant database name)."""
    if not tenant_key:
        raise ValueError("ARCADEDB_TENANT_KEY is required")
    digest = hmac.new(tenant_key.encode(), tenant_database(tenant_id).encode(), hashlib.sha256)
    return digest.hexdigest()[:40]
