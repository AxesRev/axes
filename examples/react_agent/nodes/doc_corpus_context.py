"""Load semantically relevant documentation into graph state for the current user turn."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

from aegra_api.services.doc_corpus_service import retrieve_doc_corpus_prompt_block
from examples.react_agent.context import Context
from examples.react_agent.state import State
from examples.react_agent.utils import get_message_text

logger = logging.getLogger(__name__)


def _latest_human_query(state: State) -> str:
    for message in reversed(state.messages):
        if isinstance(message, HumanMessage):
            text = get_message_text(message).strip()
            if text:
                return text
    return ""


async def load_doc_corpus_context(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Embed the latest user message and pull top-k chunks from ``doc_embedding_chunks``."""
    ctx = runtime.context
    coll_key = ctx.doc_corpus_collection_key.strip()

    query = _latest_human_query(state)
    if not query:
        logger.info("doc_corpus_context: no human message text — skipping")
        return {"doc_corpus_context": ""}

    block = await retrieve_doc_corpus_prompt_block(
        collection_key=coll_key,
        query=query,
        limit=ctx.doc_corpus_top_k,
    )
    if block:
        logger.info("doc_corpus_context: loaded %d characters", len(block))
    return {"doc_corpus_context": block}
