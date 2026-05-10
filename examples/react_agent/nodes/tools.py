import logging
from typing import Any

import tiktoken
from langchain_core.messages import ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.state import State

logger = logging.getLogger(__name__)

TOOLS: list[Any] = []

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


async def execute_tools(state: State, runtime: Runtime[Context]) -> dict[str, list[Any]]:
    """Execute tools, including GitHub MCP tools if a PAT is configured."""
    last_message = state.messages[-1]
    tool_names = [tc["name"] for tc in getattr(last_message, "tool_calls", [])]
    logger.info("Node tools: executing %d tool(s): %s", len(tool_names), tool_names)
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


async def _get_all_tools(runtime: Runtime[Context]) -> list[Any]:
    """Return the combined list of static tools + GitHub MCP tools (if PAT is set)."""
    if not runtime.context.github_pat:
        return list(TOOLS)

    client = MultiServerMCPClient(
        {
            "github": {
                "transport": "stdio",
                "command": "docker",
                "args": [
                    "run",
                    "-i",
                    "--rm",
                    "-e",
                    "GITHUB_PERSONAL_ACCESS_TOKEN",
                    "ghcr.io/github/github-mcp-server",
                ],
                "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": runtime.context.github_pat},
            }
        }
    )
    mcp_tools = await client.get_tools()
    return [*TOOLS, *mcp_tools]
