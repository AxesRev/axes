"""Permission detection subgraph.

The graph runs a three-stage pipeline:

1. ``parse_intent`` — turns the user's access request into one short hint
   per output field (``domain``, ``resource``, ``permission``).
2. ``detect_domain`` / ``detect_resource`` / ``detect_permission`` — three
   independent nodes that run in parallel. Each delegates to
   ``_field_detection_graph``, a private compiled subgraph that loops
   ``call_model -> tools -> call_model`` exactly like the original graph,
   then extracts a ``FieldResult{value, justification}``.
3. ``validate_results`` — judges the combined answer; on success the graph
   finalizes a ``Permission``, on failure it routes back to the specific
   detector(s) that produced wrong values, with feedback. Re-runs are
   capped by ``MAX_REVISIONS`` to bound the loop.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.graph import StateGraph, add_messages
from langgraph.managed import IsLastStep
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.nodes.intent_parser import parse_intent
from examples.react_agent.nodes.tools import _get_all_tools
from examples.react_agent.nodes.validator import validate_results
from examples.react_agent.prompts import (
    FIELD_DESCRIPTIONS,
    FIELD_DETECTOR_BASE_PROMPT,
    FIELD_DETECTOR_FEEDBACK_TEMPLATE,
    FIELD_DETECTOR_TASK_TEMPLATE,
    FIELD_EXTRACTOR_PROMPT,
    GITHUB_USER_CONTEXT,
)
from examples.react_agent.state import FieldResult, InputState, Permission, State
from examples.react_agent.utils import get_message_text, load_chat_model

logger = logging.getLogger(__name__)

MAX_REVISIONS: int = 3
"""Maximum number of validator-driven re-run rounds before forcing finalize."""

_FieldName = Literal["domain", "resource", "permission"]


# ---------------------------------------------------------------------------
# Internal per-field detection subgraph
# ---------------------------------------------------------------------------


@dataclass
class _FieldDetectionState:
    """State for the private per-field detection subgraph."""

    messages: Annotated[Sequence[AnyMessage], add_messages] = field(default_factory=list)
    field_name: _FieldName = "domain"
    github_repos: list[str] = field(default_factory=list)
    github_orgs: list[str] = field(default_factory=list)
    is_last_step: IsLastStep = field(default=False)
    result: FieldResult | None = field(default=None)


def _build_field_system_prompt(state: _FieldDetectionState, runtime: Runtime[Context]) -> str:
    github_user_context = (
        GITHUB_USER_CONTEXT.format(
            github_username=runtime.context.github_username,
            github_user_id=runtime.context.github_user_id,
            github_repos=", ".join(state.github_repos) if state.github_repos else "none",
            github_orgs=", ".join(state.github_orgs) if state.github_orgs else "none",
        )
        if runtime.context.github_username
        else ""
    )
    return FIELD_DETECTOR_BASE_PROMPT.format(
        field_name=state.field_name,
        field_description=FIELD_DESCRIPTIONS[state.field_name],
        github_user_context=github_user_context,
        system_time=datetime.now(tz=UTC).isoformat(),
    )


async def _call_field_model(state: _FieldDetectionState, runtime: Runtime[Context]) -> dict[str, list[AIMessage]]:
    tools = await _get_all_tools(runtime)
    model = load_chat_model(
        runtime.context.model,
        thinking_budget_tokens=runtime.context.thinking_budget_tokens,
        reasoning_effort=runtime.context.reasoning_effort,
    ).bind_tools(tools)

    response = await model.ainvoke(
        [{"role": "system", "content": _build_field_system_prompt(state, runtime)}, *state.messages]
    )
    if not isinstance(response, AIMessage):
        raise TypeError(
            f"Expected AIMessage from chat model for field {state.field_name!r}, got {type(response).__name__}"
        )

    if state.is_last_step and response.tool_calls:
        logger.warning("_call_field_model[%s]: last step reached — aborting tool calls", state.field_name)
        return {
            "messages": [
                AIMessage(
                    id=response.id,
                    content=f"Could not determine `{state.field_name}` in the allotted steps.",
                )
            ]
        }

    if response.tool_calls:
        logger.info(
            "_call_field_model[%s]: tool call(s): %s",
            state.field_name,
            [tc["name"] for tc in response.tool_calls],
        )
    else:
        logger.info("_call_field_model[%s]: finished reasoning", state.field_name)
    return {"messages": [response]}


async def _execute_field_tools(state: _FieldDetectionState, runtime: Runtime[Context]) -> dict[str, list[AnyMessage]]:
    tools = await _get_all_tools(runtime)
    tool_node = ToolNode(tools, handle_tool_errors=True)
    return cast(dict[str, list[AnyMessage]], await tool_node.ainvoke(state))


def _route_field_output(state: _FieldDetectionState) -> Literal["tools", "extract_result"]:
    last = state.messages[-1]
    if not isinstance(last, AIMessage):
        raise ValueError(f"Expected AIMessage, got {type(last).__name__} for field {state.field_name!r}")
    return "tools" if last.tool_calls else "extract_result"


async def _extract_field_result(state: _FieldDetectionState, runtime: Runtime[Context]) -> dict[str, FieldResult]:
    model = load_chat_model(runtime.context.model).with_structured_output(FieldResult)
    result = cast(
        FieldResult,
        await model.ainvoke(
            [*state.messages, {"role": "user", "content": FIELD_EXTRACTOR_PROMPT.format(field_name=state.field_name)}]
        ),
    )
    logger.info("_extract_field_result[%s]: value=%r", state.field_name, result.value)
    return {"result": result}


_field_builder = StateGraph(_FieldDetectionState, context_schema=Context)
_field_builder.add_node("call_model", _call_field_model)
_field_builder.add_node("tools", _execute_field_tools)
_field_builder.add_node("extract_result", _extract_field_result)
_field_builder.add_edge("__start__", "call_model")
_field_builder.add_conditional_edges(
    "call_model",
    _route_field_output,
    {"tools": "tools", "extract_result": "extract_result"},
)
_field_builder.add_edge("tools", "call_model")
_field_builder.add_edge("extract_result", "__end__")

_field_detection_graph = _field_builder.compile()


# ---------------------------------------------------------------------------
# Helpers shared by the three detector nodes
# ---------------------------------------------------------------------------


def _extract_user_request(state: State) -> str:
    for message in state.messages:
        if isinstance(message, HumanMessage):
            return get_message_text(message)
    raise ValueError("permission_detection: no HumanMessage found in state.messages")


def _build_seed_message(
    *, field_name: _FieldName, user_request: str, hint: str | None, feedback: str | None
) -> HumanMessage:
    feedback_block = (
        FIELD_DETECTOR_FEEDBACK_TEMPLATE.format(field_name=field_name, feedback=feedback) if feedback else ""
    )
    return HumanMessage(
        content=FIELD_DETECTOR_TASK_TEMPLATE.format(
            user_request=user_request,
            field_name=field_name,
            hint=hint or "(no hint produced — infer from the request)",
            feedback_block=feedback_block,
        )
    )


async def _run_field_detector(
    *,
    field_name: _FieldName,
    state: State,
    runtime: Runtime[Context],
    hint: str | None,
    feedback: str | None,
) -> FieldResult:
    seed = _build_seed_message(
        field_name=field_name,
        user_request=_extract_user_request(state),
        hint=hint,
        feedback=feedback,
    )
    sub_input = _FieldDetectionState(
        messages=[seed],
        field_name=field_name,
        github_repos=list(state.github_repos),
        github_orgs=list(state.github_orgs),
    )
    logger.info("detect_%s: starting (rerun=%s)", field_name, bool(feedback))
    output = await _field_detection_graph.ainvoke(sub_input, context=runtime.context)
    result: FieldResult = output["result"]
    logger.info("detect_%s: done — value=%r", field_name, result.value)
    return result


# ---------------------------------------------------------------------------
# Detector nodes
# ---------------------------------------------------------------------------


async def detect_domain(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    return {
        "domain_result": await _run_field_detector(
            field_name="domain",
            state=state,
            runtime=runtime,
            hint=state.domain_hint,
            feedback=state.domain_feedback,
        )
    }


async def detect_resource(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    return {
        "resource_result": await _run_field_detector(
            field_name="resource",
            state=state,
            runtime=runtime,
            hint=state.resource_hint,
            feedback=state.resource_feedback,
        )
    }


async def detect_permission(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    return {
        "permission_result": await _run_field_detector(
            field_name="permission",
            state=state,
            runtime=runtime,
            hint=state.permission_hint,
            feedback=state.permission_feedback,
        )
    }


# ---------------------------------------------------------------------------
# Routing & finalize
# ---------------------------------------------------------------------------


def route_validator(state: State) -> list[str]:
    """Route to specific detector(s) that need re-running, or to finalize."""
    if state.revision_count >= MAX_REVISIONS:
        logger.warning(
            "Edge route_validator: revision cap (%d) reached — forcing finalize",
            state.revision_count,
        )
        return ["finalize"]

    rerun: list[str] = []
    if state.domain_feedback:
        rerun.append("detect_domain")
    if state.resource_feedback:
        rerun.append("detect_resource")
    if state.permission_feedback:
        rerun.append("detect_permission")

    if not rerun:
        logger.info("Edge route_validator: passed — finalize")
        return ["finalize"]

    logger.info("Edge route_validator: re-running %s", rerun)
    return rerun


async def finalize(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Assemble the final ``Permission`` and emit it as a JSON AIMessage."""
    domain_value = state.domain_result.value if state.domain_result else None
    permission_value = state.permission_result.value if state.permission_result else None
    resource_value = state.resource_result.value if state.resource_result else None

    if not domain_value or not permission_value:
        logger.warning(
            "Node finalize: missing required field(s) — domain=%r permission=%r",
            domain_value,
            permission_value,
        )
        return {
            "messages": [
                AIMessage(
                    content=(
                        "Sorry, I could not determine a complete permission for this request (missing required fields)."
                    )
                )
            ]
        }

    permission = Permission(
        domain=domain_value,
        resource=resource_value,
        permission=permission_value,
    )
    logger.info(
        "Node finalize: done — domain=%r resource=%r permission=%r",
        permission.domain,
        permission.resource,
        permission.permission,
    )
    return {
        "permission": permission,
        "messages": [AIMessage(content=permission.model_dump_json())],
    }


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------

builder = StateGraph(State, input_schema=InputState, context_schema=Context)

builder.add_node("parse_intent", parse_intent)
builder.add_node("detect_domain", detect_domain)
builder.add_node("detect_resource", detect_resource)
builder.add_node("detect_permission", detect_permission)
builder.add_node("validator", validate_results)
builder.add_node("finalize", finalize)

builder.add_edge("__start__", "parse_intent")

builder.add_edge("parse_intent", "detect_domain")
builder.add_edge("parse_intent", "detect_resource")
builder.add_edge("parse_intent", "detect_permission")

builder.add_edge("detect_domain", "validator")
builder.add_edge("detect_resource", "validator")
builder.add_edge("detect_permission", "validator")

builder.add_conditional_edges(
    "validator",
    route_validator,
    ["detect_domain", "detect_resource", "detect_permission", "finalize"],
)

builder.add_edge("finalize", "__end__")

permission_detection_graph = builder.compile(name="Required Permission Agent")
