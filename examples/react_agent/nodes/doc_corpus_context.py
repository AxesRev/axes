"""Load semantically relevant documentation into graph state."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

from aegra_api.services.doc_corpus_service import retrieve_doc_corpus_prompt_block
from examples.react_agent.context import Context
from examples.react_agent.state import Permission, State
from examples.react_agent.utils import get_message_text

logger = logging.getLogger(__name__)

DocCorpusSearchPhraseResolver = Callable[[State], str]


def _latest_human_query(state: State) -> str:
    for message in reversed(state.messages):
        if isinstance(message, HumanMessage):
            text = get_message_text(message).strip()
            if text:
                return text
    return ""


def resolve_doc_corpus_search_phrase(
    state: State,
    *,
    search_phrase: str | None = None,
    search_phrase_resolver: DocCorpusSearchPhraseResolver | None = None,
) -> str:
    """Resolve the semantic-search query for doc corpus retrieval."""
    if search_phrase is not None:
        return search_phrase.strip()
    if search_phrase_resolver is not None:
        return search_phrase_resolver(state).strip()
    return _latest_human_query(state)


def grant_execution_doc_corpus_search_phrase(state: State) -> str:
    """Build a grant-focused doc search phrase from the detected permission."""
    permission = cast(Permission, state.permission)
    return f"How to grant {permission.permission} for {permission.domain}"


async def load_doc_corpus_context_with_phrase(
    state: State,
    runtime: Runtime[Context],
    *,
    search_phrase: str | None = None,
    search_phrase_resolver: DocCorpusSearchPhraseResolver | None = None,
) -> dict[str, Any]:
    """Embed *search_phrase* (or a resolver/default) and pull top-k chunks from ``doc_embedding_chunks``."""
    ctx = runtime.context
    coll_key = ctx.doc_corpus_collection_key.strip()

    query = resolve_doc_corpus_search_phrase(
        state,
        search_phrase=search_phrase,
        search_phrase_resolver=search_phrase_resolver,
    )
    if not query:
        logger.info("doc_corpus_context: empty search phrase — skipping")
        return {"doc_corpus_context": ""}

    block, hit_titles = await retrieve_doc_corpus_prompt_block(
        collection_key=coll_key,
        query=query,
        limit=ctx.doc_corpus_top_k,
    )
    if block:
        logger.info(
            "doc_corpus_context: query=%r loaded %d characters; snippet titles: %s",
            query,
            len(block),
            hit_titles,
        )
    return {"doc_corpus_context": block}


def make_load_doc_corpus_context(
    *,
    search_phrase: str | None = None,
    search_phrase_resolver: DocCorpusSearchPhraseResolver | None = None,
) -> Callable[[State, Runtime[Context]], Awaitable[dict[str, Any]]]:
    """Return a graph node that loads doc corpus context for a configurable search phrase."""

    async def load_doc_corpus_context(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
        return await load_doc_corpus_context_with_phrase(
            state,
            runtime,
            search_phrase=search_phrase,
            search_phrase_resolver=search_phrase_resolver,
        )

    if search_phrase_resolver is not None:
        load_doc_corpus_context.__name__ = "load_doc_corpus_context_resolved"
    elif search_phrase is not None:
        load_doc_corpus_context.__name__ = "load_doc_corpus_context_fixed"
    else:
        load_doc_corpus_context.__name__ = "load_doc_corpus_context"

    return load_doc_corpus_context


load_doc_corpus_context = make_load_doc_corpus_context()
