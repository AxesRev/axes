"""Smoke tests that core billing packages import after wheel layout changes."""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_import_billing_service() -> None:
    from billing.service import sum_tokens_from_usage  # noqa: PLC0415

    assert sum_tokens_from_usage({}) == 0


@pytest.mark.unit
def test_import_billing_http_handler() -> None:
    from billing.app import handler  # noqa: PLC0415

    assert callable(handler)


@pytest.mark.unit
def test_import_charge_usage_handler() -> None:
    from billing.charge_usage import handler  # noqa: PLC0415

    assert callable(handler)


@pytest.mark.unit
def test_billing_source_does_not_import_aegra_or_tenant() -> None:
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "src" / "billing"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            for module in modules:
                assert not module.startswith("aegra_api"), path
                assert not module.startswith("tenant"), path
