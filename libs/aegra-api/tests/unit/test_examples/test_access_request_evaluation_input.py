"""Regression: access_request_evaluation must receive permission from parent state."""

from unittest.mock import AsyncMock, MagicMock, patch

from examples.react_agent.context import Context
from examples.react_agent.state import AccessRequestEvaluation, Permission, State
from examples.react_agent.subgraphs.access_request_evaluation import access_request_evaluation_graph
from langchain_core.messages import AIMessage, HumanMessage


async def test_access_request_evaluation_receives_permission_from_parent_state() -> None:
    state = State(
        messages=[HumanMessage(content="Give me admin on our test repo")],
        permission=Permission(domain="github_repository", resource="AxesRev/Test_repo", permission="ADMIN"),
        github_repos=["AxesRev/Test_repo"],
        github_orgs=["AxesRev"],
    )

    with (
        patch(
            "examples.react_agent.subgraphs.access_request_evaluation.call_model",
            new=AsyncMock(return_value={"messages": [AIMessage(content="done")]}),
        ),
        patch("examples.react_agent.subgraphs.access_request_evaluation.load_chat_model") as mock_lm,
    ):
        structured_model = MagicMock()
        structured_model.ainvoke = AsyncMock(
            return_value=AccessRequestEvaluation(should_grant=False, justification="Not allowed.")
        )
        mock_model = MagicMock()
        mock_model.with_structured_output.return_value = structured_model
        mock_lm.return_value = mock_model

        output = await access_request_evaluation_graph.ainvoke(state, context=Context())

    assert output["access_evaluation"].should_grant is False
    assert output["permission"] == state.permission
