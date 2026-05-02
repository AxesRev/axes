from langgraph.graph import StateGraph

from examples.react_agent.context import Context
from examples.react_agent.edges.end import route_model_output
from examples.react_agent.nodes.llm_call import call_model
from examples.react_agent.nodes.tools import execute_tools
from examples.react_agent.state import InputState, State
from examples.react_agent.subgraphs.permission_detection import permission_detection_graph

# Define the graph
builder = StateGraph(State, input_schema=InputState, context_schema=Context)

builder.add_node("permission_detection", permission_detection_graph)
builder.add_node(call_model)
builder.add_node("tools", execute_tools)

builder.add_edge("__start__", "call_model")

builder.add_conditional_edges("call_model", route_model_output)
builder.add_edge("tools", "call_model")

graph = builder.compile(name="ReAct Agent")
