"""Tests for parameterized doc corpus context loading."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.nodes.doc_corpus_context import (
    grant_execution_doc_corpus_search_phrase,
    load_doc_corpus_context_with_phrase,
    make_load_doc_corpus_context,
    resolve_doc_corpus_search_phrase,
)
from examples.react_agent.state import Permission, State


def test_resolve_doc_corpus_search_phrase_uses_latest_human_message_by_default() -> None:
    state = State(messages=[HumanMessage(content="give me admin on repo foo")])

    phrase = resolve_doc_corpus_search_phrase(state)

    assert phrase == "give me admin on repo foo"


def test_resolve_doc_corpus_search_phrase_uses_explicit_phrase() -> None:
    state = State(messages=[HumanMessage(content="ignored")])

    phrase = resolve_doc_corpus_search_phrase(state, search_phrase="custom query")

    assert phrase == "custom query"


def test_grant_execution_doc_corpus_search_phrase_uses_permission_fields() -> None:
    state = State(
        permission=Permission(
            domain="github_repository",
            resource="org/repo",
            permission="admin",
        ),
    )

    phrase = grant_execution_doc_corpus_search_phrase(state)

    assert phrase == "How to grant admin for github_repository"


async def test_load_doc_corpus_context_with_phrase_uses_resolver() -> None:
    state = State(
        permission=Permission(domain="github_team", resource="team-a", permission="maintainer"),
    )
    runtime = Runtime(context=Context())

    with patch(
        "examples.react_agent.nodes.doc_corpus_context.retrieve_doc_corpus_prompt_block",
        new=AsyncMock(return_value=("doc block", ["Grant team access"])),
    ) as mock_retrieve:
        result = await load_doc_corpus_context_with_phrase(
            state,
            runtime,
            search_phrase_resolver=grant_execution_doc_corpus_search_phrase,
        )

    assert result == {"doc_corpus_context": "doc block"}
    mock_retrieve.assert_awaited_once_with(
        collection_key="default",
        query="How to grant maintainer for github_team",
        limit=6,
        applications=None,
    )


async def test_make_load_doc_corpus_context_default_uses_human_message() -> None:
    node = make_load_doc_corpus_context()
    state = State(messages=[HumanMessage(content="need read access")], selected_apps=["github"])
    runtime = Runtime(context=Context())

    with patch(
        "examples.react_agent.nodes.doc_corpus_context.retrieve_doc_corpus_prompt_block",
        new=AsyncMock(return_value=("", [])),
    ) as mock_retrieve:
        await node(state, runtime)

    mock_retrieve.assert_awaited_once_with(
        collection_key="default",
        query="need read access",
        limit=6,
        applications=["github"],
    )
