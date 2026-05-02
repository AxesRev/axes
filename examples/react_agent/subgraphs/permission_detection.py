from typing import cast

from langgraph.graph import StateGraph
from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.edges.end import route_model_output
from examples.react_agent.nodes.llm_call import call_model
from examples.react_agent.nodes.tools import execute_tools
from examples.react_agent.state import InputState, Permission, State
from examples.react_agent.utils import load_chat_model

# Define the graph
builder = StateGraph(State, input_schema=InputState, context_schema=Context)

builder.add_node(call_model)
builder.add_node("tools", execute_tools)


async def extract_permission(state: State, runtime: Runtime[Context]) -> dict[str, Permission]:
    """Extract structured permission from the conversation."""
    model = load_chat_model(runtime.context.model).with_structured_output(Permission)

    # We use the existing conversation to understand the permission
    response = cast(Permission, await model.ainvoke(state.messages))

    return {"permission": response}


builder.add_node(extract_permission)

builder.add_edge("__start__", "call_model")

builder.add_conditional_edges("call_model", route_model_output, {"tools": "tools", "__end__": "extract_permission"})
builder.add_edge("tools", "call_model")
builder.add_edge("extract_permission", "__end__")

permission_detection_graph = builder.compile(name="Required Permission Agent")
