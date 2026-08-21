"""Mint GitHub App installation access tokens for REST API calls."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from github import Auth, GithubIntegration
from pydantic import computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_ENV_FILE = str(Path(__file__).resolve().parents[3] / ".env")
_REPO_ROOT = Path(_ENV_FILE).parent

_token_cache: dict[str, tuple[str, int]] = {}
_REFRESH_BUFFER_SECONDS = 300


class GitHubAppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    GITHUB_APP_ID: int = 0
    GITHUB_APP_PRIVATE_KEY: str = ""
    GITHUB_APP_PRIVATE_KEY_PATH: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _load_github_private_key(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        pem = str(data.get("GITHUB_APP_PRIVATE_KEY") or "").strip()
        if pem:
            return data
        raw_path = str(data.get("GITHUB_APP_PRIVATE_KEY_PATH") or "").strip()
        if not raw_path:
            return data
        path = Path(raw_path)
        if not path.is_absolute():
            path = _REPO_ROOT / path
        if path.exists():
            data["GITHUB_APP_PRIVATE_KEY"] = path.read_text(encoding="utf-8")
        return data

    @computed_field
    @property
    def github_app_private_key(self) -> str | None:
        pem = self.GITHUB_APP_PRIVATE_KEY.strip().replace("\\n", "\n")
        return pem or None


github_settings = GitHubAppSettings()


def _github_integration() -> GithubIntegration:
    private_key = github_settings.github_app_private_key
    if github_settings.GITHUB_APP_ID <= 0 or not private_key:
        msg = "GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY are required for GitHub App auth"
        raise ValueError(msg)

    auth = Auth.AppAuth(github_settings.GITHUB_APP_ID, private_key)
    return GithubIntegration(auth=auth)


def get_installation_access_token(installation_id: str, *, api_version: str = "2022-11-28") -> str:
    """Return a cached or freshly minted installation access token."""
    del api_version

    normalized_id = installation_id.strip()
    if not normalized_id:
        msg = "github_installation_id is required for GitHub API tools"
        raise ValueError(msg)

    now = int(time.time())
    cached = _token_cache.get(normalized_id)
    if cached is not None:
        token, expires_at = cached
        if now < expires_at - _REFRESH_BUFFER_SECONDS:
            return token

    authorization = _github_integration().get_access_token(int(normalized_id))
    token = authorization.token
    if not token:
        msg = "GitHub installation access token response missing token"
        raise ValueError(msg)

    expires_at = int(authorization.expires_at.timestamp()) if authorization.expires_at else now + 3600
    _token_cache[normalized_id] = (token, expires_at)
    logger.info("github_installation_token: minted for installation_id=%s", normalized_id)
    return token
