"""Tests for ``python -m aegra_api.doc_ingest.github`` (DB ingest entrypoint)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from aegra_api.doc_ingest.github import main


def test_main_runs_ingest_and_closes_db(monkeypatch: pytest.MonkeyPatch) -> None:
    init = AsyncMock(return_value=None)
    close = AsyncMock(return_value=None)
    monkeypatch.setattr("aegra_api.doc_ingest.github.db_manager.initialize", init)
    monkeypatch.setattr("aegra_api.doc_ingest.github.db_manager.close", close)
    monkeypatch.setattr("aegra_api.doc_ingest.github.db_manager.engine", object(), raising=False)

    captured: dict[str, object] = {}

    @asynccontextmanager
    async def fake_session() -> MagicMock:
        session = MagicMock()
        captured["session"] = session
        yield session

    class _Maker:
        def __call__(self) -> object:
            return fake_session()

    monkeypatch.setattr(
        "aegra_api.doc_ingest.github.get_metadata_session_maker",
        lambda: _Maker(),
    )

    async def fake_ingest(session: object) -> tuple[int, int, list[str]]:
        captured["ingest_session"] = session
        return (1, 4, ["GitHub Docs", "GitHub Docs", "GitHub Docs", "GitHub Docs"])

    monkeypatch.setattr(
        "aegra_api.doc_ingest.github.ingest_github_documentation_from_zip",
        fake_ingest,
    )

    assert main() == 0
    init.assert_awaited_once()
    close.assert_awaited_once()
    assert captured["ingest_session"] is captured["session"]


def test_main_nonzero_on_init_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom() -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr("aegra_api.doc_ingest.github.db_manager.initialize", boom)
    close = AsyncMock(return_value=None)
    monkeypatch.setattr("aegra_api.doc_ingest.github.db_manager.close", close)
    monkeypatch.setattr("aegra_api.doc_ingest.github.db_manager.engine", None, raising=False)

    assert main() == 1
    close.assert_not_called()
