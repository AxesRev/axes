"""Tests for tenant context injection into access evaluation LLM calls."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from examples.react_agent.context import Context
from examples.react_agent.nodes.llm_call import call_model
from examples.react_agent.prompts import ACCESS_EVALUATION_BASE_PROMPT
from examples.react_agent.state import State
from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime


async def test_call_model_includes_tenant_context_in_evaluation_prompt() -> None:
    state = State(
        messages=[HumanMessage(content="Give me admin")],
        tenant_agent_context="Never grant admin without manager approval.",
    )
    runtime = Runtime(context=Context(system_prompt=ACCESS_EVALUATION_BASE_PROMPT))

    captured_messages: list[list[object]] = []

    async def fake_get_all_tools(_runtime: Runtime[Context]) -> list[object]:
        return []

    mock_model = MagicMock()
    mock_bound = MagicMock()
    mock_bound.ainvoke = AsyncMock(
        side_effect=lambda messages: captured_messages.append(messages) or MagicMock(tool_calls=[])
    )
    mock_model.bind_tools.return_value = mock_bound

    with (
        patch("examples.react_agent.nodes.llm_call._get_all_tools", new=fake_get_all_tools),
        patch("examples.react_agent.nodes.llm_call.load_chat_model", return_value=mock_model),
        patch(
            "examples.react_agent.nodes.llm_call.datetime",
            wraps=datetime,
        ) as mock_datetime,
    ):
        mock_datetime.now.return_value = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
        await call_model(state, runtime)

    system_message = captured_messages[0][0]
    assert system_message["role"] == "system"
    assert "Never grant admin without manager approval." in system_message["content"]
    assert "Tenant-specific policy and instructions" in system_message["content"]
