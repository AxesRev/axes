"""Permission detection subgraph.

The graph runs a three-stage pipeline:

1. ``parse_intent`` — turns the user's access request into one short hint
   per output field (``domain``, ``resource``, ``permission``).
2. ``detect_domain`` / ``detect_resource`` / ``detect_permission`` — three
   independent per-field detector nodes that run in parallel. Each node
   internally loops ``call_model -> tools -> call_model`` until the LLM stops
   requesting tools, then extracts a ``FieldResult{value, justification}``.
3. ``validate_results`` — judges the combined answer; on success the graph
   finalizes a ``Permission``, on failure it routes back to the specific
   detector(s) that produced wrong values, with feedback. Re-runs are
   capped by ``MAX_REVISIONS`` to bound the loop.
"""

from __future__ import annotations

import logging
from collections.abc import MutableSequence
from datetime import UTC, datetime
from typing import Any, Literal, cast

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.graph import StateGraph
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

MAX_TOOL_STEPS: int = 20
"""Maximum tool-call iterations inside a single detector node run."""

_FieldName = Literal["domain", "resource", "permission"]


# ---------------------------------------------------------------------------
# Helpers shared by the three detector nodes
# ---------------------------------------------------------------------------


def _extract_user_request(state: State) -> str:
    for message in state.messages:
        if isinstance(message, HumanMessage):
            return get_message_text(message)
    raise ValueError("permission_detection: no HumanMessage found in state.messages")


def _build_github_user_context(state: State, runtime: Runtime[Context]) -> str:
    if not runtime.context.github_username:
        return ""
    return GITHUB_USER_CONTEXT.format(
        github_username=runtime.context.github_username,
        github_user_id=runtime.context.github_user_id,
        github_repos=", ".join(state.github_repos) if state.github_repos else "none",
        github_orgs=", ".join(state.github_orgs) if state.github_orgs else "none",
    )


def _build_field_system_prompt(field_name: _FieldName, state: State, runtime: Runtime[Context]) -> str:
    if field_name not in FIELD_DESCRIPTIONS:
        raise ValueError(f"Unknown field_name: {field_name!r}")
    return FIELD_DETECTOR_BASE_PROMPT.format(
        field_name=field_name,
        field_description=FIELD_DESCRIPTIONS[field_name],
        github_user_context=_build_github_user_context(state, runtime),
        system_time=datetime.now(tz=UTC).isoformat(),
    )


def _build_seed_message(
    *, field_name: _FieldName, user_request: str, hint: str | None, feedback: str | None
) -> HumanMessage:
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


async def _run_field_loop(
    *,
    field_name: _FieldName,
    state: State,
    runtime: Runtime[Context],
    hint: str | None,
    feedback: str | None,
) -> FieldResult:
    """Run the call-model → tools → call-model loop for one field.

    Builds a private message list seeded with the task description, runs up to
    ``MAX_TOOL_STEPS`` iterations of LLM + tool execution, then does a final
    structured-output pass to extract ``FieldResult``.
    """
    user_request = _extract_user_request(state)
    seed = _build_seed_message(
        field_name=field_name,
        user_request=user_request,
        hint=hint,
        feedback=feedback,
    )

    messages: MutableSequence[AnyMessage] = [seed]
    tools = await _get_all_tools(runtime)
    model = load_chat_model(
        runtime.context.model,
        thinking_budget_tokens=runtime.context.thinking_budget_tokens,
        reasoning_effort=runtime.context.reasoning_effort,
    ).bind_tools(tools)
    system_message = _build_field_system_prompt(field_name, state, runtime)
    tool_node = ToolNode(tools, handle_tool_errors=True)

    for step in range(MAX_TOOL_STEPS):
        response = await model.ainvoke([{"role": "system", "content": system_message}, *messages])
        if not isinstance(response, AIMessage):
            raise TypeError(
                f"Expected AIMessage from chat model for field {field_name!r}, got {type(response).__name__}"
            )
        messages.append(response)

        if not response.tool_calls:
            logger.info(
                "detect_%s step %d: LLM finished reasoning",
                field_name,
                step,
            )
            break

        tool_names = [tc["name"] for tc in response.tool_calls]
        logger.info(
            "detect_%s step %d: executing %d tool(s): %s",
            field_name,
            step,
            len(tool_names),
            tool_names,
        )
        tool_result = await tool_node.ainvoke({"messages": list(messages)})
        messages.extend(tool_result["messages"])
    else:
        logger.warning(
            "detect_%s: reached MAX_TOOL_STEPS (%d) without a final answer",
            field_name,
            MAX_TOOL_STEPS,
        )

    extractor = load_chat_model(runtime.context.model).with_structured_output(FieldResult)
    extractor_prompt = FIELD_EXTRACTOR_PROMPT.format(field_name=field_name)
    result = cast(
        FieldResult,
        await extractor.ainvoke([*messages, {"role": "user", "content": extractor_prompt}]),
    )

    logger.info("detect_%s: extracted value=%r", field_name, result.value)
    return result


# ---------------------------------------------------------------------------
# Detector nodes
# ---------------------------------------------------------------------------


async def detect_domain(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    logger.info("Node detect_domain: starting (rerun=%s)", bool(state.domain_feedback))
    result = await _run_field_loop(
        field_name="domain",
        state=state,
        runtime=runtime,
        hint=state.domain_hint,
        feedback=state.domain_feedback,
    )
    return {"domain_result": result}


async def detect_resource(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    logger.info("Node detect_resource: starting (rerun=%s)", bool(state.resource_feedback))
    result = await _run_field_loop(
        field_name="resource",
        state=state,
        runtime=runtime,
        hint=state.resource_hint,
        feedback=state.resource_feedback,
    )
    return {"resource_result": result}


async def detect_permission(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    logger.info("Node detect_permission: starting (rerun=%s)", bool(state.permission_feedback))
    result = await _run_field_loop(
        field_name="permission",
        state=state,
        runtime=runtime,
        hint=state.permission_hint,
        feedback=state.permission_feedback,
    )
    return {"permission_result": result}


# ---------------------------------------------------------------------------
# Routing & finalize
# ---------------------------------------------------------------------------


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
