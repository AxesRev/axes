"""Auth0 bearer tokens for billing Lambda (no FastAPI)."""

from __future__ import annotations

import jwt
from slack_app.auth0 import _decode_auth0_token

from billing.errors import HttpError


def claims_from_authorization(authorization: str | None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HttpError(401, "Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HttpError(401, "Missing bearer token")
    try:
        return _decode_auth0_token(token)
    except RuntimeError as exc:
        raise HttpError(503, str(exc)) from exc
    except jwt.PyJWTError as exc:
        raise HttpError(401, "Invalid access token") from exc
