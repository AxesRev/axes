from typing import Literal

from langgraph.graph import StateGraph

from examples.react_agent.context import Context
from examples.react_agent.nodes.doc_corpus_context import load_doc_corpus_context
from examples.react_agent.nodes.user_context import load_user_context
from examples.react_agent.state import InputState, State
from examples.react_agent.subgraphs.access_request_evaluation import access_request_evaluation_graph
from examples.react_agent.subgraphs.permission_detection import permission_detection_graph


def route_after_permission_detection(state: State) -> Literal["access_request_evaluation", "__end__"]:
    if state.permission is not None:
        return "access_request_evaluation"

    return "__end__"


# Define the graph

builder = StateGraph(State, input_schema=InputState, context_schema=Context)


builder.add_node(load_user_context)

builder.add_node(load_doc_corpus_context)

builder.add_node("permission_detection", permission_detection_graph)

builder.add_node("access_request_evaluation", access_request_evaluation_graph)


builder.add_edge("__start__", "load_user_context")

builder.add_edge("load_user_context", "load_doc_corpus_context")

builder.add_edge("load_doc_corpus_context", "permission_detection")

builder.add_conditional_edges(
    "permission_detection",
    route_after_permission_detection,
    ["access_request_evaluation", "__end__"],
)

builder.add_edge("access_request_evaluation", "__end__")


graph = builder.compile(name="ReAct Agent")
