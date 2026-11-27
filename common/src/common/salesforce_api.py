"""Pin every Salesforce client to the newest REST API version the org offers.

simple_salesforce falls back to its own built-in default version, which lags Salesforce releases, so
newer fields (for example PermissionSet system permissions) are invisible. ``/services/data/`` lists
every version the org supports; we reconnect on the newest one, reusing the session.
"""

from __future__ import annotations

from typing import Any


def latest_api_version(versions: list[dict[str, Any]]) -> str:
    """Return the highest ``version`` from a ``/services/data/`` response, e.g. ``'66.0'``."""
    return max((str(item["version"]) for item in versions), key=lambda v: tuple(int(p) for p in v.split(".")))


def with_latest_api_version[Client](sf: Client) -> Client:
    """Return a client on the same session, switched to the org's newest API version."""
    response = sf.session.get(  # type: ignore[attr-defined]
        f"https://{sf.sf_instance}/services/data/",  # type: ignore[attr-defined]
        headers=sf.headers,  # type: ignore[attr-defined]
        timeout=30,
    )
    response.raise_for_status()
    version = latest_api_version(response.json())
    return type(sf)(  # type: ignore[call-arg]
        session_id=sf.session_id,  # type: ignore[attr-defined]
        instance=sf.sf_instance,  # type: ignore[attr-defined]
        version=version,
    )
