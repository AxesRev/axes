"""Single-field detection subgraph.

This subgraph runs the same `call_model -> tools -> call_model` loop as the
original permission detection graph, but specialized for one of the three
output fields (`domain`, `resource`, or `permission`). The orchestrator
invokes one instance per field in parallel and reads each `result` back into
the parent state.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated, Literal, cast

from langchain_core.messages import AIMessage, AnyMessage
from langgraph.graph import StateGraph, add_messages
from langgraph.managed import IsLastStep
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.nodes.tools import _get_all_tools
from examples.react_agent.prompts import (
    FIELD_DESCRIPTIONS,
    FIELD_DETECTOR_BASE_PROMPT,
    FIELD_EXTRACTOR_PROMPT,
    GITHUB_USER_CONTEXT,
)
from examples.react_agent.state import FieldResult
from examples.react_agent.utils import load_chat_model

logger = logging.getLogger(__name__)


@dataclass
class FieldDetectionState:
    """Internal state of a per-field detection subgraph.

    Parent passes in `field_name`, the seed user message (already including
    the hint and optional validator feedback), and the github context. The
    subgraph runs its own tool loop and writes the answer to `result`.
    """

    messages: Annotated[Sequence[AnyMessage], add_messages] = field(default_factory=list)
    field_name: Literal["domain", "resource", "permission"] = "domain"
    github_repos: list[str] = field(default_factory=list)
    github_orgs: list[str] = field(default_factory=list)
    is_last_step: IsLastStep = field(default=False)
    result: FieldResult | None = field(default=None)


def _build_github_user_context(state: FieldDetectionState, runtime: Runtime[Context]) -> str:
    if not runtime.context.github_username:
        return ""
    return GITHUB_USER_CONTEXT.format(
        github_username=runtime.context.github_username,
        github_user_id=runtime.context.github_user_id,
        github_repos=", ".join(state.github_repos) if state.github_repos else "none",
        github_orgs=", ".join(state.github_orgs) if state.github_orgs else "none",
    )


def _build_field_system_prompt(state: FieldDetectionState, runtime: Runtime[Context]) -> str:
    if state.field_name not in FIELD_DESCRIPTIONS:
        raise ValueError(f"Unknown field_name: {state.field_name!r}")
    return FIELD_DETECTOR_BASE_PROMPT.format(
        field_name=state.field_name,
        field_description=FIELD_DESCRIPTIONS[state.field_name],
        github_user_context=_build_github_user_context(state, runtime),
        system_time=datetime.now(tz=UTC).isoformat(),
    )


async def call_field_model(state: FieldDetectionState, runtime: Runtime[Context]) -> dict[str, list[AIMessage]]:
    """Run one tool-calling step of the per-field detector loop."""
    logger.info(
        "Node call_field_model[%s]: starting (messages: %d)",
        state.field_name,
        len(state.messages),
    )
    tools = await _get_all_tools(runtime)
    model = load_chat_model(
        runtime.context.model,
        thinking_budget_tokens=runtime.context.thinking_budget_tokens,
        reasoning_effort=runtime.context.reasoning_effort,
    ).bind_tools(tools)

    system_message = _build_field_system_prompt(state, runtime)
    response = await model.ainvoke([{"role": "system", "content": system_message}, *state.messages])
    if not isinstance(response, AIMessage):
        raise TypeError(
            f"Expected AIMessage from chat model, got {type(response).__name__} for field {state.field_name!r}"
        )

    if state.is_last_step and response.tool_calls:
        logger.warning(
            "Node call_field_model[%s]: reached last step with pending tool calls — aborting",
            state.field_name,
        )
        return {
            "messages": [
                AIMessage(
                    id=response.id,
                    content=(
                        f"Sorry, I could not determine the `{state.field_name}` field in the specified number of steps."
                    ),
                )
            ]
        }

    if response.tool_calls:
        logger.info(
            "Node call_field_model[%s]: requested %d tool call(s): %s",
            state.field_name,
            len(response.tool_calls),
            [tc["name"] for tc in response.tool_calls],
        )
    else:
        logger.info("Node call_field_model[%s]: produced final reasoning message", state.field_name)
    return {"messages": [response]}


async def execute_field_tools(state: FieldDetectionState, runtime: Runtime[Context]) -> dict[str, list[AnyMessage]]:
    """Execute the tool calls requested by the most recent assistant message."""
    last_message = state.messages[-1]
    tool_names = [tc["name"] for tc in getattr(last_message, "tool_calls", [])]
    logger.info(
        "Node tools[%s]: executing %d tool(s): %s",
        state.field_name,
        len(tool_names),
        tool_names,
    )
    tools = await _get_all_tools(runtime)
    tool_node = ToolNode(tools, handle_tool_errors=True)
    result = cast(dict[str, list[AnyMessage]], await tool_node.ainvoke(state))
    logger.info("Node tools[%s]: done", state.field_name)
    return result


def route_field_output(state: FieldDetectionState) -> Literal["tools", "extract_result"]:
    """Loop into tools while the LLM keeps calling them, otherwise extract."""
    last_message = state.messages[-1]
    if not isinstance(last_message, AIMessage):
        raise ValueError(
            f"Expected AIMessage at end of detector turn for {state.field_name!r}, got {type(last_message).__name__}"
        )
    if last_message.tool_calls:
        return "tools"
    return "extract_result"


async def extract_field_result(state: FieldDetectionState, runtime: Runtime[Context]) -> dict[str, FieldResult]:
    """Coerce the detector's free-form conclusion into a structured `FieldResult`."""
    logger.info("Node extract_result[%s]: starting structured extraction", state.field_name)
    model = load_chat_model(runtime.context.model).with_structured_output(FieldResult)
    extractor_prompt = FIELD_EXTRACTOR_PROMPT.format(field_name=state.field_name)

    response = cast(
        FieldResult,
        await model.ainvoke([*state.messages, {"role": "user", "content": extractor_prompt}]),
    )

    logger.info(
        "Node extract_result[%s]: done — value=%r",
        state.field_name,
        response.value,
    )
    return {"result": response}


_builder = StateGraph(FieldDetectionState, context_schema=Context)
_builder.add_node("call_model", call_field_model)
_builder.add_node("tools", execute_field_tools)
_builder.add_node("extract_result", extract_field_result)
_builder.add_edge("__start__", "call_model")
_builder.add_conditional_edges(
    "call_model",
    route_field_output,
    {"tools": "tools", "extract_result": "extract_result"},
)
_builder.add_edge("tools", "call_model")
_builder.add_edge("extract_result", "__end__")

field_detection_graph = _builder.compile(name="Field Detection")
