"""Tests for ``python -m app_integrations.salesforce`` (DB ingest entrypoint)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app_integrations.salesforce.__main__ import main


def test_main_runs_ingest_and_closes_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "docs.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    init = AsyncMock(return_value=None)
    close = AsyncMock(return_value=None)
    monkeypatch.setattr("app_integrations.salesforce.__main__.db_manager.initialize", init)
    monkeypatch.setattr("app_integrations.salesforce.__main__.db_manager.close", close)
    monkeypatch.setattr("app_integrations.salesforce.__main__.db_manager.engine", object(), raising=False)

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
        "app_integrations.salesforce.__main__.get_metadata_session_maker",
        lambda: _Maker(),
    )

    async def fake_ingest(session: object, path: Path) -> tuple[int, int, list[str]]:
        captured["ingest_session"] = session
        captured["pdf_path"] = path
        return (1, 2, ["Introduction to REST API", "Introduction to REST API"])

    monkeypatch.setattr(
        "app_integrations.salesforce.__main__.ingest_salesforce_documentation_from_pdf",
        fake_ingest,
    )

    assert main([str(pdf_path)]) == 0
    init.assert_awaited_once()
    close.assert_awaited_once()
    assert captured["ingest_session"] is captured["session"]
    assert captured["pdf_path"] == pdf_path


def test_main_usage_without_pdf_path() -> None:
    assert main([]) == 1


def test_main_nonzero_on_init_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "docs.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    async def boom() -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr("app_integrations.salesforce.__main__.db_manager.initialize", boom)
    close = AsyncMock(return_value=None)
    monkeypatch.setattr("app_integrations.salesforce.__main__.db_manager.close", close)
    monkeypatch.setattr("app_integrations.salesforce.__main__.db_manager.engine", None, raising=False)

    assert main([str(pdf_path)]) == 1
    close.assert_not_called()
