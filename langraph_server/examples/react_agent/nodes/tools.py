import json
import logging
import os
from typing import Any

import tiktoken
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.state import State

logger = logging.getLogger(__name__)

TOOLS: list[Any] = []
_READ_TOOL_NAME = "read_neo4j_cypher"

_MAX_TOOL_RESULT_TOKENS = 10_000
_TOO_LARGE_MESSAGE = (
    "Tool call result was too large (exceeded {token_count:,} tokens). Narrow down your search and try again."
)


def _get_encoder(model: str) -> tiktoken.Encoding:
    model_name = model.split("/", 1)[-1]
    try:
        return tiktoken.encoding_for_model(model_name)
    except KeyError:
        return tiktoken.encoding_for_model("gpt-4o")


def _truncate_if_oversized(message: ToolMessage, encoder: tiktoken.Encoding) -> ToolMessage:
    content_str = message.content if isinstance(message.content, str) else str(message.content)
    token_count = len(encoder.encode(content_str))
    if token_count <= _MAX_TOOL_RESULT_TOKENS:
        return message
    logger.warning(
        "Node tools: tool result for call_id=%s is %d tokens — replacing with truncation notice",
        message.tool_call_id,
        token_count,
    )
    return ToolMessage(
        content=_TOO_LARGE_MESSAGE.format(token_count=token_count),
        tool_call_id=message.tool_call_id,
        name=message.name,
    )


async def execute_tools(
    state: State,
    runtime: Runtime[Context],
    *,
    tools: list[Any] | None = None,
) -> dict[str, list[Any]]:
    """Execute tools (Neo4j MCP over HTTP when configured, plus static TOOLS)."""
    last_message = state.messages[-1]
    tool_names = [tc["name"] for tc in getattr(last_message, "tool_calls", [])]
    logger.info("Node tools: executing %d tool(s): %s", len(tool_names), tool_names)
    if tools is None:
        tools = await _get_all_tools(runtime)
    tool_node = ToolNode(tools, handle_tool_errors=True)
    encoder = _get_encoder(runtime.context.model)
    result: dict[str, list[Any]] = await tool_node.ainvoke(state)  # type: ignore[return-value]
    result["messages"] = [
        _truncate_if_oversized(msg, encoder) if isinstance(msg, ToolMessage) else msg
        for msg in result.get("messages", [])
    ]
    logger.info("Node tools: done")
    return result


def _mcp_servers() -> dict[str, dict[str, Any]]:
    servers: dict[str, dict[str, Any]] = {}

    neo4j_host = os.environ.get("NEO4J_MCP_HOST", "").strip()
    if neo4j_host:
        servers["neo4j"] = {"transport": "http", "url": f"{neo4j_host.rstrip('/')}/mcp/"}

    return servers


async def _get_all_tools(_runtime: Runtime[Context]) -> list[Any]:
    """Static TOOLS plus MCP tools when ``NEO4J_MCP_HOST`` is set."""
    servers = _mcp_servers()
    if not servers:
        return list(TOOLS)

    client = MultiServerMCPClient(servers)
    mcp_tools = await client.get_tools()
    return [*TOOLS, *mcp_tools]


def _extract_tool_text(result: Any) -> str:
    content = result[0] if isinstance(result, tuple) else result
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)


async def _get_read_neo4j_tool() -> BaseTool | None:
    servers = _mcp_servers()
    if not servers:
        return None

    client = MultiServerMCPClient(servers)
    tools = await client.get_tools()
    for tool in tools:
        if tool.name == _READ_TOOL_NAME:
            return tool
    logger.warning("%s tool not found on Neo4j MCP server", _READ_TOOL_NAME)
    return None


async def read_neo4j_cypher(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Execute a read Cypher query via the configured Neo4j MCP server."""
    read_tool = await _get_read_neo4j_tool()
    if read_tool is None:
        raise RuntimeError("NEO4J_MCP_HOST is not configured or read_neo4j_cypher is unavailable")

    result = await read_tool.ainvoke({"query": query, "params": params or {}})
    text = _extract_tool_text(result).strip()
    if not text:
        return []

    parsed = json.loads(text)
    if not isinstance(parsed, list):
        raise ValueError("read_neo4j_cypher returned non-list JSON")
    return parsed
