from __future__ import annotations

import pytest
from fastmcp.server.middleware import MiddlewareContext
from fastmcp.tools.tool import ToolResult
from mcp.types import CallToolRequestParams, TextContent

from neo4j_mcp.server import ReturnToolErrorsMiddleware


def _text(result: ToolResult) -> str:
    parts: list[str] = []
    for block in result.content:
        if isinstance(block, TextContent):
            parts.append(block.text)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "\n".join(parts)


@pytest.mark.unit
async def test_tool_valueerror_is_returned_as_text() -> None:
    middleware = ReturnToolErrorsMiddleware()
    context = MiddlewareContext(
        message=CallToolRequestParams(
            name="read_neo4j_cypher",
            arguments={"query": "CREATE (n)"},
        ),
        method="tools/call",
    )

    async def boom(_context: MiddlewareContext[CallToolRequestParams]) -> ToolResult:
        raise ValueError("Only MATCH queries are allowed for read-query")

    result = await middleware.on_call_tool(context, boom)

    text = _text(result)
    assert "read_neo4j_cypher" in text
    assert "Only MATCH queries are allowed for read-query" in text


@pytest.mark.unit
async def test_successful_tool_result_is_passed_through() -> None:
    middleware = ReturnToolErrorsMiddleware()
    context = MiddlewareContext(
        message=CallToolRequestParams(name="read_neo4j_cypher", arguments={"query": "MATCH (n) RETURN n"}),
        method="tools/call",
    )
    expected = ToolResult(content="[]")

    async def ok(_context: MiddlewareContext[CallToolRequestParams]) -> ToolResult:
        return expected

    result = await middleware.on_call_tool(context, ok)

    assert result is expected
