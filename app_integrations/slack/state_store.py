"""OAuth state store that carries tenant_id through the Slack install flow."""

from __future__ import annotations

import logging
import os
import time
from logging import Logger
from pathlib import Path
from uuid import uuid4

from slack_sdk.oauth.state_store.async_state_store import AsyncOAuthStateStore


class TenantOAuthStateStore(AsyncOAuthStateStore):
    """Issues OAuth state tokens and associates each with a tenant_id until consumed."""

    def __init__(
        self,
        *,
        expiration_seconds: int,
        base_dir: str = str(Path.home()) + "/.axes-slack-oauth-state",
        client_id: str | None = None,
        logger: Logger | None = None,
    ) -> None:
        self.expiration_seconds = expiration_seconds
        self.base_dir = base_dir
        if client_id is not None:
            self.base_dir = f"{self.base_dir}/{client_id}"
        self._logger = logger or logging.getLogger(__name__)
        self._tenant_by_state: dict[str, str] = {}

    @property
    def logger(self) -> Logger:
        return self._logger

    async def async_issue(self, *args: object, tenant_id: str | None = None, **kwargs: object) -> str:
        return self.issue(tenant_id=tenant_id)

    async def async_consume(self, state: str) -> bool:
        return self.consume(state)

    def issue(self, *, tenant_id: str | None = None) -> str:
        state = str(uuid4())
        self._mkdir(self.base_dir)
        filepath = f"{self.base_dir}/{state}"
        with open(filepath, "w", encoding="utf-8") as file:
            file.write(f"{time.time()}|{tenant_id or ''}")
        return state

    def consume(self, state: str) -> bool:
        filepath = f"{self.base_dir}/{state}"
        try:
            with open(filepath, encoding="utf-8") as file:
                created_str, tenant_id = file.read().split("|", 1)
                created = float(created_str)
                still_valid = time.time() < created + self.expiration_seconds
            os.remove(filepath)
            if still_valid and tenant_id:
                self._tenant_by_state[state] = tenant_id
            return still_valid
        except (FileNotFoundError, ValueError) as exc:
            self.logger.warning("Failed to consume OAuth state %s: %s", state, exc)
            return False

    def pop_tenant_id(self, state: str) -> str | None:
        return self._tenant_by_state.pop(state, None)

    @staticmethod
    def _mkdir(path: str | Path) -> None:
        Path(path).mkdir(parents=True, exist_ok=True)
