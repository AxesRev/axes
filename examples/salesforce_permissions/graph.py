"""Salesforce Permission Request Agent with MCP integration.

This is a simple ReAct agent that helps users understand Salesforce permissions by:
1. Understanding natural language permission requests
2. Querying Salesforce using MCP tools to find matching permission sets
3. Suggesting appropriate permissions with explanations
"""

from datetime import UTC, datetime
from typing import Literal, cast

from langchain_core.messages import AIMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime

from .context import Context
from .state import InputState, State
from .utils import load_chat_model


async def get_mcp_tools(runtime: Runtime[Context]) -> list:
    """Get tools from Salesforce MCP server.

    Args:
        runtime: Runtime context containing Salesforce org configuration.

    Returns:
        List of tools from the MCP server.
    """
    # Initialize MCP client with Salesforce server
    # This uses the Salesforce MCP server via stdio transport
    client = MultiServerMCPClient(
        {
            "salesforce": {
                "transport": "stdio",
                "command": "npx",
                "args": [
                    "-y",
                    "@modelcontextprotocol/server-salesforce",
                ],
                "env": {
                    "SF_TARGET_ORG": runtime.context.salesforce_org,
                },
            }
        }
    )

    return await client.get_tools()


async def call_model(state: State, runtime: Runtime[Context]) -> dict[str, list[AIMessage]]:
    """Call the LLM to analyze the permission request.

    The model will use Salesforce MCP tools to query available permissions
    and suggest appropriate permission sets.

    Args:
        state: The current state of the conversation.
        runtime: Runtime context containing configuration.

    Returns:
        Dictionary containing the model's response message.
    """
    # Load tools from MCP server
    tools = await get_mcp_tools(runtime)

    # Initialize the model with MCP tools
    model = load_chat_model(runtime.context.model).bind_tools(tools)

    # Format the system prompt
    system_message = runtime.context.system_prompt.format(
        system_time=datetime.now(tz=UTC).isoformat(), salesforce_org=runtime.context.salesforce_org
    )

    # Get the model's response
    response = cast(
        "AIMessage",
        await model.ainvoke([{"role": "system", "content": system_message}, *state.messages]),
    )

    return {"messages": [response]}


async def execute_tools(state: State, runtime: Runtime[Context]) -> dict[str, list]:
    """Execute Salesforce MCP tools to gather permission information.

    Args:
        state: The current state with tool calls to execute.
        runtime: Runtime context.

    Returns:
        Dictionary containing tool execution results.
    """
    # Load tools from MCP server
    tools = await get_mcp_tools(runtime)

    # Create a tool node and execute
    tool_node = ToolNode(tools)
    result = await tool_node.ainvoke(state)

    return result


# Build the graph

builder = StateGraph(State, input_schema=InputState, context_schema=Context)

# Add nodes
builder.add_node(call_model)
builder.add_node("tools", execute_tools)

# Set the entrypoint
builder.add_edge("__start__", "call_model")


def route_model_output(state: State) -> Literal["tools", "__end__"]:
    """Determine the next node based on the model's output.

    If the model wants to use tools, route to tools node.
    If the model has a final response, end the graph.
    """
    last_message = state.messages[-1]
    if not isinstance(last_message, AIMessage):
        raise ValueError(f"Expected AIMessage in output edges, but got {type(last_message).__name__}")

    # If the model has tool calls, execute them
    if last_message.tool_calls:
        return "tools"

    # Otherwise, the model has a final response - end
    return "__end__"


# Add conditional edges
builder.add_conditional_edges("call_model", route_model_output, path_map=["tools", END])

# After executing tools, go back to the model
builder.add_edge("tools", "call_model")

# Compile the graph
graph = builder.compile(name="Salesforce Permissions Agent")
