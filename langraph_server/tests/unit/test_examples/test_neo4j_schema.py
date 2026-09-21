"""Tests for injecting the Neo4j schema into agent prompts."""

from unittest.mock import AsyncMock, patch

from examples.react_agent.neo4j_schema_prompt import build_neo4j_schema_block
from examples.react_agent.nodes.neo4j_schema import load_neo4j_schema
from examples.react_agent.prompts import ACCESS_EVALUATION_BASE_PROMPT, PERMISSION_DETECTOR_BASE_PROMPT
from examples.react_agent.state import State


def test_build_neo4j_schema_block_returns_empty_for_blank_schema() -> None:
    assert build_neo4j_schema_block("") == ""
    assert build_neo4j_schema_block("  \n") == ""


def test_build_neo4j_schema_block_includes_schema_text() -> None:
    schema = '{"AppIdentity": {"properties": {"external_id": {"type": "STRING"}}}}'
    block = build_neo4j_schema_block(schema)
    assert schema in block


def test_prompts_include_schema_block() -> None:
    block = build_neo4j_schema_block('{"AppIdentity": {}}')
    shared = {
        "system_time": "2026-09-21T00:00:00+00:00",
        "user_context": "",
        "doc_corpus_context": "",
        "neo4j_schema": block,
        "tenant_agent_context": "",
    }
    assert '{"AppIdentity": {}}' in PERMISSION_DETECTOR_BASE_PROMPT.format(**shared)
    assert '{"AppIdentity": {}}' in ACCESS_EVALUATION_BASE_PROMPT.format(**shared)


async def test_load_neo4j_schema_stores_fetched_text() -> None:
    schema = '{"AppIdentity": {"type": "node"}}'
    with patch(
        "examples.react_agent.nodes.neo4j_schema.fetch_neo4j_schema",
        new=AsyncMock(return_value=schema),
    ):
        result = await load_neo4j_schema(State())

    assert result == {"neo4j_schema": schema}


async def test_load_neo4j_schema_returns_empty_when_fetch_fails() -> None:
    with patch(
        "examples.react_agent.nodes.neo4j_schema.fetch_neo4j_schema",
        new=AsyncMock(side_effect=RuntimeError("mcp down")),
    ):
        result = await load_neo4j_schema(State())

    assert result == {"neo4j_schema": ""}
