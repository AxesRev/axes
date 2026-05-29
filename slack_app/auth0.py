"""Auth0 token validation for slack_app HTTP routes."""

from __future__ import annotations

import jwt
from fastapi import HTTPException, Request, status
from jwt import PyJWKClient

from slack_app.config import slack_settings

_jwks_client: PyJWKClient | None = None


def _auth0_issuer() -> str:
    domain = slack_settings.AUTH0_DOMAIN.strip()
    if not domain:
        msg = "AUTH0_DOMAIN must be configured"
        raise RuntimeError(msg)
    return f"https://{domain}/"


def _accepted_audiences() -> list[str]:
    audiences: list[str] = []
    client_id = slack_settings.AUTH0_CLIENT_ID.strip()
    api_audience = slack_settings.AUTH0_AUDIENCE.strip()
    if client_id:
        audiences.append(client_id)
    if api_audience:
        audiences.append(api_audience)
    if not audiences:
        msg = "AUTH0_CLIENT_ID or AUTH0_AUDIENCE must be configured"
        raise RuntimeError(msg)
    return audiences


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is not None:
        return _jwks_client
    domain = slack_settings.AUTH0_DOMAIN.strip()
    if not domain:
        msg = "AUTH0_DOMAIN must be configured"
        raise RuntimeError(msg)
    _jwks_client = PyJWKClient(f"https://{domain}/.well-known/jwks.json")
    return _jwks_client


def _decode_auth0_token(token: str) -> dict:
    signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
    last_error: jwt.PyJWTError | None = None
    for audience in _accepted_audiences():
        try:
            decoded = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=audience,
                issuer=_auth0_issuer(),
            )
            if isinstance(decoded, dict):
                return decoded
        except jwt.PyJWTError as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    msg = "Token validation failed"
    raise RuntimeError(msg)


async def require_auth0_claims(request: Request) -> dict:
    """FastAPI dependency that validates an Auth0 ID or access token and returns claims."""
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    try:
        return _decode_auth0_token(token)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
        ) from exc
