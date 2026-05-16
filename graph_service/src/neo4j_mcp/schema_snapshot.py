"""Live Neo4j schema snapshot via ``CALL db.schema.visualization()``."""

from __future__ import annotations

import json
from typing import Any

from neo4j import AsyncDriver
from neo4j.graph import Node as NeoNode
from neo4j.graph import Relationship as NeoRelationship

_VIS_QUERY = (
    "CALL db.schema.visualization() "
    "YIELD nodes, relationships "
    "RETURN nodes AS viz_nodes, relationships AS viz_relationships"
)


def _serialize_schema_node(node: NeoNode) -> dict[str, Any]:
    props = dict(node)
    labels = sorted(node.labels)
    name = props.get("name")
    return {
        "labels": labels,
        "name": name,
        "indexes": props.get("indexes", []),
        "constraints": props.get("constraints", []),
    }


def _serialize_schema_relationship(rel: NeoRelationship) -> dict[str, Any]:
    start_n, end_n = rel.nodes
    return {
        "type": rel.type,
        "start": {"labels": sorted(start_n.labels)},
        "end": {"labels": sorted(end_n.labels)},
    }


def visualization_row_to_schematic(row: dict[str, Any]) -> dict[str, Any]:
    """Turn one procedure row into a stable JSON-serializable schematic."""
    nodes_raw = row.get("viz_nodes") or []
    rels_raw = row.get("viz_relationships") or []
    return {
        "procedure": "db.schema.visualization",
        "nodes": [_serialize_schema_node(n) for n in nodes_raw],
        "relationships": [_serialize_schema_relationship(r) for r in rels_raw],
    }


async def fetch_schema_visualization_schematic(
    *,
    driver: AsyncDriver,
    database: str,
) -> dict[str, Any]:
    """Run ``db.schema.visualization()`` and return a schematic dict."""
    records, _summary, _keys = await driver.execute_query(
        _VIS_QUERY,
        database_=database,
    )
    if not records:
        raise ValueError("CALL db.schema.visualization() returned no rows")

    return visualization_row_to_schematic(dict(records[0]))


def schematic_to_json(schematic: dict[str, Any]) -> str:
    """Pretty JSON for embedding in MCP tool descriptions."""
    return json.dumps(schematic, indent=2, sort_keys=True)


def build_run_cypher_tool_description(*, schema_json: str, read_only: bool) -> str:
    """Full MCP tool description: fixed instructions + live schematic JSON."""
    mode = (
        "Read-only mode is ON: mutating keywords (CREATE, MERGE, DELETE, SET, REMOVE, DROP, DETACH DELETE) are rejected."
        if read_only
        else "Read-only mode is OFF: write queries are allowed — use with care."
    )
    return (
        "Execute parameterized read/write Cypher against this server's Neo4j database.\n\n"
        'Results are returned as JSON {"rows": [...], "row_count": N}. Always prefer parameters ($map) over string concatenation.\n\n'
        f"{mode}\n\n"
        "Live schema snapshot (CALL db.schema.visualization(), schematic JSON):\n\n"
        f"```json\n{schema_json}\n```"
    )
