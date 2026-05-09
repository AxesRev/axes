"""Permission detection subgraph.

The graph runs a three-stage pipeline:

1. ``parse_intent`` — turns the user's access request into one short hint
   per output field (``domain``, ``resource``, ``permission``).
2. ``detect_domain`` / ``detect_resource`` / ``detect_permission`` — three
   independent per-field detectors that run in parallel, each looping
   ``call_model -> tools -> call_model`` (via the field detection subgraph)
   and producing a ``FieldResult{value, justification}``.
3. ``validate_results`` — judges the combined answer; on success the graph
   finalizes a ``Permission``, on failure it routes back to the specific
   detector(s) that produced wrong values, with feedback. Re-runs are
   capped by ``MAX_REVISIONS`` to bound the loop.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import StateGraph
from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.nodes.intent_parser import parse_intent
from examples.react_agent.nodes.validator import validate_results
from examples.react_agent.prompts import (
    FIELD_DETECTOR_FEEDBACK_TEMPLATE,
    FIELD_DETECTOR_TASK_TEMPLATE,
)
from examples.react_agent.state import InputState, Permission, State
from examples.react_agent.subgraphs.field_detection import FieldDetectionState, field_detection_graph
from examples.react_agent.utils import get_message_text

logger = logging.getLogger(__name__)

MAX_REVISIONS: int = 3
"""Maximum number of validator-driven re-run rounds before forcing finalize."""

_FieldName = Literal["domain", "resource", "permission"]


def _extract_user_request(state: State) -> str:
    for message in state.messages:
        if isinstance(message, HumanMessage):
            return get_message_text(message)
    raise ValueError("permission_detection: no HumanMessage found in state.messages")


def _build_field_seed_message(
    *, field_name: _FieldName, user_request: str, hint: str | None, feedback: str | None
) -> HumanMessage:
    """Build the initial HumanMessage handed to a field detection subgraph."""
    feedback_block = (
        FIELD_DETECTOR_FEEDBACK_TEMPLATE.format(field_name=field_name, feedback=feedback) if feedback else ""
    )
    content = FIELD_DETECTOR_TASK_TEMPLATE.format(
        user_request=user_request,
        field_name=field_name,
        hint=hint or "(no hint produced — infer from the request)",
        feedback_block=feedback_block,
    )
    return HumanMessage(content=content)


async def _run_field_detector(
    *,
    field_name: _FieldName,
    state: State,
    runtime: Runtime[Context],
    hint: str | None,
    feedback: str | None,
) -> dict[str, Any]:
    """Invoke the field detection subgraph for one field and return a parent-state update."""
    user_request = _extract_user_request(state)
    seed = _build_field_seed_message(
        field_name=field_name,
        user_request=user_request,
        hint=hint,
        feedback=feedback,
    )
    sub_input = FieldDetectionState(
        messages=[seed],
        field_name=field_name,
        github_repos=list(state.github_repos),
        github_orgs=list(state.github_orgs),
    )
    logger.info(
        "Subgraph detect_%s: starting (rerun=%s)",
        field_name,
        bool(feedback),
    )
    output = await field_detection_graph.ainvoke(sub_input, context=runtime.context)
    result = output.get("result")
    logger.info(
        "Subgraph detect_%s: done — value=%r",
        field_name,
        getattr(result, "value", None),
    )
    return {f"{field_name}_result": result}


async def detect_domain(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    return await _run_field_detector(
        field_name="domain",
        state=state,
        runtime=runtime,
        hint=state.domain_hint,
        feedback=state.domain_feedback,
    )


async def detect_resource(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    return await _run_field_detector(
        field_name="resource",
        state=state,
        runtime=runtime,
        hint=state.resource_hint,
        feedback=state.resource_feedback,
    )


async def detect_permission(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    return await _run_field_detector(
        field_name="permission",
        state=state,
        runtime=runtime,
        hint=state.permission_hint,
        feedback=state.permission_feedback,
    )


def route_validator(state: State) -> list[str]:
    """Decide which detector(s) to re-run based on validator feedback.

    Returns a list of next-node keys (LangGraph activates all of them in the
    next superstep). When all feedback fields are clear, or when the revision
    cap has been reached, routes to ``finalize`` instead.
    """
    if state.revision_count >= MAX_REVISIONS:
        logger.warning(
            "Edge route_validator: revision cap reached (%d) — forcing finalize",
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
        logger.info("Edge route_validator: validation passed — finalize")
        return ["finalize"]

    logger.info("Edge route_validator: re-running %s", rerun)
    return rerun


async def finalize(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Assemble the final ``Permission`` and emit it as a JSON AIMessage.

    Preserves the existing API contract that callers (e.g. the Slack handler)
    can read the permission JSON from ``state.messages[-1].content``.
    """
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
