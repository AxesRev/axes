"""Unit tests for ``run_cypher`` guard and execution wiring."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from neo4j_mcp.tools import cypher


@pytest.mark.unit
async def test_run_cypher_rejects_mutating_query_when_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cypher,
        "get_settings",
        lambda: SimpleNamespace(allow_write_queries=False, neo4j_database="neo4j"),
    )
    ctx = MagicMock()
    with pytest.raises(ValueError, match="Write/mutating"):
        await cypher.run_cypher("CREATE (n:Tmp)", ctx=ctx)


@pytest.mark.unit
async def test_run_cypher_allows_match_when_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cypher,
        "get_settings",
        lambda: SimpleNamespace(allow_write_queries=False, neo4j_database="neo4j"),
    )

    driver = MagicMock()
    driver.execute_query = AsyncMock(return_value=([], MagicMock(), []))

    ctx = MagicMock()
    ctx.request_context.lifespan_context = SimpleNamespace(driver=driver)

    result = await cypher.run_cypher("MATCH (n) RETURN n LIMIT 1", ctx=ctx)

    driver.execute_query.assert_awaited_once()
    assert '"row_count": 0' in result
