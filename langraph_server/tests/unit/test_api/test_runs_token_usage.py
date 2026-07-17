"""Unit tests for run token usage persistence."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.callbacks import UsageMetadataCallbackHandler

from aegra_api.api.runs import execute_run_async, update_run_status
from aegra_api.models import User


@pytest.fixture
def mock_user() -> User:
    return User(identity="test-user", display_name="Test User", permissions=[])


@pytest.mark.asyncio
async def test_execute_run_async_persists_token_usage_on_run(
    mock_user: User,
) -> None:
    run_id = str(uuid4())
    thread_id = str(uuid4())
    graph_id = "test-graph"
    context = {"tenant_id": "tenant-1"}

    usage_callback = UsageMetadataCallbackHandler()
    usage_callback.usage_metadata = {
        "gpt-4o-mini": {
            "input_tokens": 8,
            "output_tokens": 10,
            "total_tokens": 18,
            "input_token_details": {"audio": 0, "cache_read": 0},
            "output_token_details": {"audio": 0, "reasoning": 0},
        },
    }

    async def successful_stream():
        yield ("values", {"messages": []})

    mock_session = AsyncMock()

    with (
        patch("aegra_api.api.runs.get_langgraph_service") as mock_lg_service,
        patch(
            "aegra_api.api.runs.stream_graph_events",
            return_value=successful_stream(),
        ),
        patch("aegra_api.api.runs.update_run_status", new_callable=AsyncMock) as mock_update_status,
        patch("aegra_api.api.runs.set_thread_status", new_callable=AsyncMock),
        patch("aegra_api.api.runs.attach_usage_metadata_callback") as mock_attach_callback,
        patch("aegra_api.api.runs._get_session_maker") as mock_session_maker,
        patch("aegra_api.api.runs.streaming_service.cleanup_run", new_callable=AsyncMock),
    ):
        mock_graph = MagicMock()
        mock_lg_service.return_value.get_graph.return_value.__aenter__ = AsyncMock(return_value=mock_graph)
        mock_lg_service.return_value.get_graph.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_attach_callback.return_value = ({}, usage_callback)
        mock_session_maker.return_value = lambda: mock_session

        await execute_run_async(
            run_id=run_id,
            thread_id=thread_id,
            graph_id=graph_id,
            input_data={},
            user=mock_user,
            config={},
            context=context,
            stream_mode=["values"],
            session=mock_session,
        )

    success_call = mock_update_status.await_args_list[-1]
    assert success_call.args[0] == run_id
    assert success_call.args[1] == "success"
    assert success_call.kwargs["token_usage"] == usage_callback.usage_metadata
    assert "context" not in success_call.kwargs


@pytest.mark.asyncio
async def test_update_run_status_persists_token_usage() -> None:
    mock_session = AsyncMock()
    token_usage = {
        "gpt-4o-mini": {
            "input_tokens": 8,
            "output_tokens": 10,
            "total_tokens": 18,
        },
    }

    with patch("aegra_api.api.runs._get_session_maker") as mock_session_maker:
        mock_session_maker.return_value = lambda: mock_session

        await update_run_status(
            "run-123",
            "success",
            output={"messages": []},
            token_usage=token_usage,
        )

    execute_call = mock_session.execute.await_args
    values = execute_call.args[0].compile().params
    assert values["token_usage"] == token_usage
