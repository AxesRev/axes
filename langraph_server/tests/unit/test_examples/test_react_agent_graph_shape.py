"""Regression: LangGraph edges must use node name strings, not callables."""


def test_react_agent_graph_imports_and_compiles() -> None:
    from examples.react_agent.graph import graph

    assert graph.name == "ReAct Agent"
