"""Auth0 token validation for tenant HTTP routes."""

from __future__ import annotations

import jwt
from jwt import PyJWKClient

from tenants.config import tenant_settings
from tenants.errors import HttpError

_jwks_client: PyJWKClient | None = None


def _auth0_issuer() -> str:
    domain = tenant_settings.AUTH0_DOMAIN.strip()
    if not domain:
        raise HttpError(503, "AUTH0_DOMAIN must be configured")
    return f"https://{domain}/"


def _id_token_audience() -> str:
    client_id = tenant_settings.AUTH0_CLIENT_ID.strip()
    if not client_id:
        raise HttpError(503, "AUTH0_CLIENT_ID must be configured")
    return client_id


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is not None:
        return _jwks_client
    domain = tenant_settings.AUTH0_DOMAIN.strip()
    if not domain:
        raise HttpError(503, "AUTH0_DOMAIN must be configured")
    _jwks_client = PyJWKClient(f"https://{domain}/.well-known/jwks.json")
    return _jwks_client


def claims_from_bearer(authorization: str | None) -> dict[str, object]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HttpError(401, "Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HttpError(401, "Missing bearer token")
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        decoded = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=_id_token_audience(),
            issuer=_auth0_issuer(),
        )
    except RuntimeError as exc:
        raise HttpError(503, str(exc)) from exc
    except jwt.PyJWTError as exc:
        raise HttpError(401, "Invalid access token") from exc
    if not isinstance(decoded, dict):
        raise HttpError(401, "Invalid access token")
    return decoded
