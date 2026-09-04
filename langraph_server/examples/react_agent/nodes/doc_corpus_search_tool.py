from __future__ import annotations

from langchain.tools import ToolRuntime, tool

from aegra_api.core.orm import get_metadata_session_maker
from aegra_api.services.doc_corpus_service import search_doc_chunks_by_string
from examples.react_agent.context import Context
from examples.react_agent.state import State


def _selected_apps(state: object) -> list[str] | None:
    if isinstance(state, dict):
        return state.get("selected_apps")
    return getattr(state, "selected_apps", None)


@tool
async def search_docs_by_string(
    query: str,
    runtime: ToolRuntime[Context, State],
    limit: int = 20,
) -> list[dict[str, str | None]]:
    """Search ingested documentation by exact substring (case-insensitive). This is not semantic search; unmatched strings return no results."""
    async with get_metadata_session_maker()() as session:
        hits = await search_doc_chunks_by_string(
            session,
            collection_key=runtime.context.doc_corpus_collection_key,
            query=query,
            limit=limit,
            applications=_selected_apps(runtime.state),
        )
    return [{"application": hit.application, "page_title": hit.page_title, "content": hit.content} for hit in hits]
