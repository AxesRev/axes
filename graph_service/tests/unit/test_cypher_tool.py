"""Unit tests for ``run_cypher`` guard and execution wiring."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from neo4j_mcp.schemas import RunCypherOutput
from neo4j_mcp.tools import cypher


@pytest.mark.unit
async def test_run_cypher_rejects_mutating_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cypher,
        "get_settings",
        lambda: SimpleNamespace(neo4j_database="neo4j"),
    )
    ctx = MagicMock()
    with pytest.raises(ValueError, match="Only read-only"):
        await cypher.run_cypher("CREATE (n:Tmp)", ctx=ctx)


@pytest.mark.unit
async def test_run_cypher_returns_structured_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cypher,
        "get_settings",
        lambda: SimpleNamespace(neo4j_database="neo4j"),
    )

    driver = MagicMock()
    driver.execute_query = AsyncMock(return_value=([], MagicMock(), []))

    ctx = MagicMock()
    ctx.request_context.lifespan_context = SimpleNamespace(driver=driver)

    result = await cypher.run_cypher("MATCH (n) RETURN n LIMIT 1", ctx=ctx)

    driver.execute_query.assert_awaited_once()
    assert isinstance(result, RunCypherOutput)
    assert result.row_count == 0
    assert result.rows == []
