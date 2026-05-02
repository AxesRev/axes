from langgraph.graph import StateGraph

from examples.react_agent.context import Context
from examples.react_agent.state import InputState, State
from examples.react_agent.subgraphs.permission_detection import permission_detection_graph

# Define the graph
builder = StateGraph(State, input_schema=InputState, context_schema=Context)

builder.add_node("permission_detection", permission_detection_graph)
# builder.add_node(call_model)
# builder.add_node("tools", execute_tools)

builder.add_edge("__start__", "permission_detection")

# builder.add_conditional_edges("call_model", route_model_output, {"tools": "tools", "__end__": "permission_detection"})
# builder.add_edge("tools", "call_model")
builder.add_edge("permission_detection", "__end__")
graph = builder.compile(name="ReAct Agent")
