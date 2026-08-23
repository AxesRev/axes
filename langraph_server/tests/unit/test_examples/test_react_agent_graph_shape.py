"""Regression: LangGraph edges must use node name strings, not callables."""

from unittest.mock import AsyncMock, patch


async def test_react_agent_graph_imports_and_compiles() -> None:
    with patch(
        "examples.react_agent.subgraphs.permission_detection._get_all_tools",
        new=AsyncMock(return_value=[]),
    ):
        from examples.react_agent.graph import graph

        compiled = await graph()
        assert compiled.name == "ReAct Agent"
