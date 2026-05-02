"""Define a custom Reasoning and Action agent.

Works with a chat model with tool calling support.
"""

from datetime import UTC, datetime
from typing import Any, Literal, cast

from langchain_core.messages import AIMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime

from react_agent.context import Context
from react_agent.prompts import GITHUB_USER_CONTEXT
from react_agent.state import InputState, State
from react_agent.tools import TOOLS
from react_agent.utils import load_chat_model


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


async def call_model(state: State, runtime: Runtime[Context]) -> dict[str, list[AIMessage]]:
    """Call the LLM powering our "agent"."""
    tools = await _get_all_tools(runtime)
    model = load_chat_model(runtime.context.model).bind_tools(tools)

    system_message = runtime.context.system_prompt.format(
        system_time=datetime.now(tz=UTC).isoformat(),
        github_user_context=(
            GITHUB_USER_CONTEXT.format(
                github_username=runtime.context.github_username,
                github_user_id=runtime.context.github_user_id,
            )
            if runtime.context.github_username
            else ""
        ),
    )

    response = cast(
        "AIMessage",
        await model.ainvoke([{"role": "system", "content": system_message}, *state.messages]),
    )

    if state.is_last_step and response.tool_calls:
        return {
            "messages": [
                AIMessage(
                    id=response.id,
                    content="Sorry, I could not find an answer to your question in the specified number of steps.",
                )
            ]
        }

    return {"messages": [response]}


async def execute_tools(state: State, runtime: Runtime[Context]) -> dict[str, list[Any]]:
    """Execute tools, including GitHub MCP tools if a PAT is configured."""
    tools = await _get_all_tools(runtime)
    tool_node = ToolNode(tools)
    return await tool_node.ainvoke(state)  # type: ignore[return-value]


# Define the graph
builder = StateGraph(State, input_schema=InputState, context_schema=Context)

builder.add_node(call_model)
builder.add_node("tools", execute_tools)

builder.add_edge("__start__", "call_model")


def route_model_output(state: State) -> Literal["__end__", "tools"]:
    """Route to tools node or end based on whether the model made tool calls."""
    last_message = state.messages[-1]
    if not isinstance(last_message, AIMessage):
        raise ValueError(f"Expected AIMessage in output edges, but got {type(last_message).__name__}")
    if not last_message.tool_calls:
        return "__end__"
    return "tools"


builder.add_conditional_edges("call_model", route_model_output)
builder.add_edge("tools", "call_model")

graph = builder.compile(name="ReAct Agent")
