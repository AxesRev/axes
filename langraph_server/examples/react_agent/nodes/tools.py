import logging
from typing import Any

import tiktoken
from langchain_core.messages import ToolMessage
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.graph_db import graph_tools
from examples.react_agent.nodes.doc_corpus_search_tool import search_docs_by_string
from examples.react_agent.state import State

logger = logging.getLogger(__name__)

TOOLS: list[Any] = [search_docs_by_string]

_MAX_TOOL_RESULT_TOKENS = 30_000
_TOO_LARGE_MESSAGE = "Result was too large, use the tool with more narrow filters"


def _get_encoder(model: str) -> tiktoken.Encoding:
    model_name = model.split("/", 1)[-1]
    try:
        return tiktoken.encoding_for_model(model_name)
    except KeyError:
        return tiktoken.encoding_for_model("gpt-4o")


def truncate_tool_text(content: str, *, encoder: tiktoken.Encoding | None = None) -> str:
    """Drop oversized tool output and tell the model to retry with narrower filters."""
    enc = encoder or _get_encoder("gpt-4o")
    token_count = len(enc.encode(content))
    if token_count <= _MAX_TOOL_RESULT_TOKENS:
        return content
    logger.warning(
        "tool result exceeded %d tokens (%d) — returning too-large error", _MAX_TOOL_RESULT_TOKENS, token_count
    )
    return _TOO_LARGE_MESSAGE


def truncate_tool_message(message: ToolMessage, *, encoder: tiktoken.Encoding | None = None) -> ToolMessage:
    content_str = message.content if isinstance(message.content, str) else str(message.content)
    truncated = truncate_tool_text(content_str, encoder=encoder)
    if truncated is content_str:
        return message
    return ToolMessage(
        content=truncated,
        tool_call_id=message.tool_call_id,
        name=message.name,
    )


def _truncate_if_oversized(message: ToolMessage, encoder: tiktoken.Encoding) -> ToolMessage:
    return truncate_tool_message(message, encoder=encoder)


async def execute_tools(
    state: State,
    runtime: Runtime[Context],
    *,
    tools: list[Any] | None = None,
) -> dict[str, list[Any]]:
    """Execute tools (tenant graph tools via ArcadeDB MCP, plus static TOOLS)."""
    last_message = state.messages[-1]
    tool_names = [tc["name"] for tc in getattr(last_message, "tool_calls", [])]
    logger.info("Node tools: executing %d tool(s): %s", len(tool_names), tool_names)
    if tools is None:
        tools = await _get_all_tools(runtime)
    tool_node = ToolNode(tools, handle_tool_errors=True)
    encoder = _get_encoder(runtime.context.model)
    result: dict[str, list[Any]] = await tool_node.ainvoke(state)  # type: ignore[return-value]
    result["messages"] = [
        _truncate_if_oversized(msg, encoder) if isinstance(msg, ToolMessage) else msg
        for msg in result.get("messages", [])
    ]
    logger.info("Node tools: done")
    return result


async def _get_all_tools(runtime: Runtime[Context] | None = None) -> list[Any]:
    """Static TOOLS plus the tenant's ArcadeDB graph tools (MCP, read-only, pinned to its database)."""
    tenant_id = runtime.context.tenant_id.strip() if runtime is not None else ""
    if not tenant_id:
        return list(TOOLS)
    try:
        return [*TOOLS, *await graph_tools(tenant_id)]
    except Exception:
        logger.exception("graph tools unavailable for tenant_id=%s", tenant_id)
        return list(TOOLS)
