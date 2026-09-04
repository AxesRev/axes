from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.tools import ToolRuntime

from aegra_api.models.doc_corpus import DocCorpusSearchHit
from examples.react_agent.context import Context
from examples.react_agent.nodes.doc_corpus_search_tool import search_docs_by_string
from examples.react_agent.nodes.tools import TOOLS, _get_all_tools
from examples.react_agent.state import State
from examples.react_agent.subgraphs.permission_detection import PermissionDetectorState


def _runtime(state: object | None = None) -> ToolRuntime:
    return ToolRuntime(
        state=state if state is not None else State(selected_apps=["salesforce"]),
        context=Context(doc_corpus_collection_key="default"),
        config={},
        stream_writer=MagicMock(),
        tool_call_id="1",
        store=None,
    )


@pytest.mark.asyncio
async def test_search_docs_by_string_uses_selected_apps_from_state() -> None:
    session = MagicMock()
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "examples.react_agent.nodes.doc_corpus_search_tool.get_metadata_session_maker",
            return_value=lambda: session_cm,
        ),
        patch(
            "examples.react_agent.nodes.doc_corpus_search_tool.search_doc_chunks_by_string",
            new=AsyncMock(return_value=[]),
        ) as mock_search,
    ):
        result = await search_docs_by_string.coroutine(
            query="needle",
            runtime=_runtime(),
        )

    assert result == []
    kwargs = mock_search.await_args.kwargs
    assert kwargs["query"] == "needle"
    assert kwargs["applications"] == ["salesforce"]
    assert kwargs["limit"] == 20


@pytest.mark.asyncio
async def test_search_docs_by_string_uses_selected_apps_from_detector_state() -> None:
    session = MagicMock()
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=None)
    detector_state: PermissionDetectorState = {
        "messages": [],
        "selected_apps": ["github", "salesforce"],
    }

    with (
        patch(
            "examples.react_agent.nodes.doc_corpus_search_tool.get_metadata_session_maker",
            return_value=lambda: session_cm,
        ),
        patch(
            "examples.react_agent.nodes.doc_corpus_search_tool.search_doc_chunks_by_string",
            new=AsyncMock(return_value=[]),
        ) as mock_search,
    ):
        await search_docs_by_string.coroutine(
            query="needle",
            runtime=_runtime(detector_state),
        )

    assert mock_search.await_args.kwargs["applications"] == ["github", "salesforce"]


@pytest.mark.asyncio
async def test_search_docs_by_string_formats_hits() -> None:
    session = MagicMock()
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=None)
    hit = DocCorpusSearchHit(
        application="salesforce",
        page_title="needle",
        content="body",
        score=1.0,
    )

    with (
        patch(
            "examples.react_agent.nodes.doc_corpus_search_tool.get_metadata_session_maker",
            return_value=lambda: session_cm,
        ),
        patch(
            "examples.react_agent.nodes.doc_corpus_search_tool.search_doc_chunks_by_string",
            new=AsyncMock(return_value=[hit]),
        ),
    ):
        result = await search_docs_by_string.coroutine(
            query="needle",
            runtime=_runtime(),
            limit=4,
        )

    assert result == [
        {"application": "salesforce", "page_title": "needle", "content": "body"},
    ]


@pytest.mark.asyncio
async def test_get_all_tools_includes_search_docs_by_string() -> None:
    with patch("examples.react_agent.nodes.tools._mcp_servers", return_value={}):
        tools = await _get_all_tools()

    assert tools[0].name == "search_docs_by_string"
    assert search_docs_by_string in TOOLS
