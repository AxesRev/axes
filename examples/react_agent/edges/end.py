from typing import Literal

from langchain_core.messages import AIMessage

from examples.react_agent.state import State


def route_model_output(state: State) -> Literal["__end__", "tools"]:
    """Route to tools node or end based on whether the model made tool calls."""
    last_message = state.messages[-1]
    if not isinstance(last_message, AIMessage):
        raise ValueError(f"Expected AIMessage in output edges, but got {type(last_message).__name__}")
    if not last_message.tool_calls:
        return "__end__"
    return "tools"
