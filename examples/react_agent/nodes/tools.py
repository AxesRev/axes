import logging
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.state import State

logger = logging.getLogger(__name__)

TOOLS: list[Any] = []


async def execute_tools(state: State, runtime: Runtime[Context]) -> dict[str, list[Any]]:
    """Execute tools, including GitHub MCP tools if a PAT is configured."""
    last_message = state.messages[-1]
    tool_names = [tc["name"] for tc in getattr(last_message, "tool_calls", [])]
    logger.info("Node tools: executing %d tool(s): %s", len(tool_names), tool_names)
    tools = await _get_all_tools(runtime)
    tool_node = ToolNode(tools, handle_tool_errors=True)
    result = await tool_node.ainvoke(state)  # type: ignore[return-value]
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
