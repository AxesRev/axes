from langgraph.graph import StateGraph

from examples.react_agent.context import Context
from examples.react_agent.nodes.github_context import load_github_context
from examples.react_agent.state import InputState, State
from examples.react_agent.subgraphs.permission_detection import permission_detection_graph

# Define the graph
builder = StateGraph(State, input_schema=InputState, context_schema=Context)

builder.add_node(load_github_context)
builder.add_node("permission_detection", permission_detection_graph)

builder.add_edge("__start__", "load_github_context")
builder.add_edge("load_github_context", "permission_detection")
builder.add_edge("permission_detection", "__end__")

graph = builder.compile(name="ReAct Agent")
