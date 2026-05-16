"""Unit tests for schema visualization schematic builders."""

from __future__ import annotations

import pytest

from neo4j_mcp.schema_snapshot import visualization_row_to_schematic


@pytest.mark.unit
def test_visualization_row_empty_lists() -> None:
    row = {"viz_nodes": [], "viz_relationships": []}
    doc = visualization_row_to_schematic(row)
    assert doc["procedure"] == "db.schema.visualization"
    assert doc["nodes"] == []
    assert doc["relationships"] == []
