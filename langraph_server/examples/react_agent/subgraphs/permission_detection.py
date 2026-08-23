"""Permission detection subgraph."""

from __future__ import annotations

import dataclasses
import logging
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command

from examples.react_agent.context import Context
from examples.react_agent.nodes.llm_call import call_model
from examples.react_agent.nodes.tools import _get_all_tools, execute_tools
from examples.react_agent.nodes.validator import validate_results
from examples.react_agent.prompts import (
    PERMISSION_DETECTOR_BASE_PROMPT,
    PERMISSION_DETECTOR_FEEDBACK_TEMPLATE,
    PERMISSION_DETECTOR_TASK_TEMPLATE,
)
from examples.react_agent.state import FieldResult, InputState, Permission, State
from examples.react_agent.utils import get_message_text

logger = logging.getLogger(__name__)

MAX_REVISIONS: int = 3
SUBMIT_TOOL_NAME = "submit_detected_permission"

_RESOURCE_DETECTOR_GROUP_LIMIT: int = 20
_RESOURCE_DETECTOR_PERMISSION_LIMIT: int = 50


# ---------------------------------------------------------------------------
# Submit / routing tool
# ---------------------------------------------------------------------------


@tool
def submit_detected_permission(
    domain: str,
    permission: str,
    domain_justification: str,
    permission_justification: str,
    resource: str | None = None,
    resource_justification: str = "",
) -> str:
    """Submit the detected domain, resource, and permission and send them to the validator.

    Call this tool alone, only when you have determined all three fields.
    Pass resource as null when the request is not for a specific named entity.
    """
    return "submitted"


def _command_from_submit(tool_call: dict[str, Any], other_calls: list[dict[str, Any]]) -> Command:
    args = tool_call.get("args") or {}
    domain = args.get("domain")
    permission = args.get("permission")
    resource = args.get("resource")
    domain_justification = args.get("domain_justification") or ""
    permission_justification = args.get("permission_justification") or ""
    resource_justification = args.get("resource_justification") or ("No specific resource." if not resource else "")
    logger.info(
        "submit_detected_permission: domain=%r resource=%r permission=%r",
        domain,
        resource,
        permission,
    )
    messages: list[ToolMessage] = [
        ToolMessage(
            content="Ignored: submit_detected_permission was called in the same turn.",
            tool_call_id=other["id"],
            name=other["name"],
        )
        for other in other_calls
    ]
    messages.append(
        ToolMessage(
            content="Submitted detected permission fields for validation.",
            tool_call_id=tool_call["id"],
            name=SUBMIT_TOOL_NAME,
        )
    )
    return Command(
        update={
            "domain_result": FieldResult(value=domain, justification=domain_justification),
            "resource_result": FieldResult(value=resource, justification=resource_justification),
            "permission_result": FieldResult(value=permission, justification=permission_justification),
            "messages": messages,
        },
        goto="validator",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extra_detector_context(state: State) -> str:
    """Add the user's current group and resource-access data."""
    if not state.user_contexts:
        return ""

    sections: list[str] = []
    for user_context in state.user_contexts:
        if user_context.groups:
            group_lines = "\n".join(
                group.format_for_context() for group in user_context.groups[:_RESOURCE_DETECTOR_GROUP_LIMIT]
            )
            sections.append(f"Groups this user currently belongs to ({user_context.app}):\n{group_lines}")

        resource_permissions = [
            permission for permission in user_context.permissions if permission.target_kind == "resource"
        ]
        if resource_permissions:
            permission_lines = "\n".join(
                f"- {permission.target_name}: {permission.permission}"
                for permission in resource_permissions[:_RESOURCE_DETECTOR_PERMISSION_LIMIT]
            )
            sections.append(
                f"Resources this user currently has access to ({user_context.app}; present state only):\n"
                + permission_lines
            )

    if not sections:
        return ""

    return "\n\n" + "\n\n".join(sections)


def _feedback_block(state: State) -> str:
    lines: list[str] = []
    if state.domain_feedback:
        lines.append(f"- domain: {state.domain_feedback}")
    if state.resource_feedback:
        lines.append(f"- resource: {state.resource_feedback}")
    if state.permission_feedback:
        lines.append(f"- permission: {state.permission_feedback}")
    if not lines:
        return ""
    return PERMISSION_DETECTOR_FEEDBACK_TEMPLATE.format(feedback="\n".join(lines))


def _seed(state: State) -> HumanMessage:
    user_request = next(
        (get_message_text(message) for message in state.messages if isinstance(message, HumanMessage)), ""
    )
    base_content = PERMISSION_DETECTOR_TASK_TEMPLATE.format(
        user_request=user_request,
        feedback_block=_feedback_block(state),
    )
    return HumanMessage(content=base_content + _extra_detector_context(state))


async def _detection_tools(runtime: Runtime[Context]) -> list[Any]:
    return [submit_detected_permission, *(await _get_all_tools(runtime))]


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def seed_detection(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    logger.info("seed_detection: starting permission detection")
    return {"messages": [_seed(state)]}


async def call_detection_model(state: State, runtime: Runtime[Context]) -> dict[str, list[AIMessage]]:
    tools = await _detection_tools(runtime)
    detection_runtime = Runtime(
        context=dataclasses.replace(runtime.context, system_prompt=PERMISSION_DETECTOR_BASE_PROMPT),
    )
    return await call_model(state, detection_runtime, tools=tools)


def route_after_model(state: State) -> Literal["tools", "finalize"]:
    last_message = state.messages[-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        logger.info("route_after_model: call_model -> tools")
        return "tools"
    logger.warning("route_after_model: no tool calls — finalize")
    return "finalize"


async def execute_detection_tools(state: State, runtime: Runtime[Context]) -> dict[str, Any] | Command:
    last_message = state.messages[-1]
    tool_calls = list(getattr(last_message, "tool_calls", []))
    submit_calls = [call for call in tool_calls if call.get("name") == SUBMIT_TOOL_NAME]
    if submit_calls:
        other_calls = [call for call in tool_calls if call.get("name") != SUBMIT_TOOL_NAME]
        return _command_from_submit(submit_calls[0], other_calls)
    return await execute_tools(state, runtime)


async def inject_feedback(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    logger.info("inject_feedback: sending validator feedback back to detector")
    return {"messages": [_seed(state)]}


def route_validator(state: State) -> Literal["inject_feedback", "finalize"]:
    if state.revision_count >= MAX_REVISIONS:
        logger.warning("route_validator: revision cap (%d) — forcing finalize", state.revision_count)
        return "finalize"

    if state.domain_feedback or state.resource_feedback or state.permission_feedback:
        logger.info("route_validator: feedback present — re-running detector")
        return "inject_feedback"

    logger.info("route_validator: passed — finalize")
    return "finalize"


async def finalize(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    domain_value = state.domain_result.value if state.domain_result else None
    permission_value = state.permission_result.value if state.permission_result else None
    resource_value = state.resource_result.value if state.resource_result else None

    if not domain_value or not permission_value:
        logger.warning("finalize: missing required field(s) — domain=%r permission=%r", domain_value, permission_value)
        return {
            "messages": [
                AIMessage(
                    content="Sorry, I could not determine a complete permission for this request (missing required fields)."
                )
            ]
        }

    permission = Permission(domain=domain_value, resource=resource_value, permission=permission_value)
    logger.info(
        "finalize: domain=%r resource=%r permission=%r", permission.domain, permission.resource, permission.permission
    )
    return {
        "permission": permission,
        "messages": [AIMessage(content=permission.model_dump_json())],
    }


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

builder = StateGraph(State, input_schema=InputState, context_schema=Context)

builder.add_node("seed_detection", seed_detection)
builder.add_node("call_model", call_detection_model)
builder.add_node("tools", execute_detection_tools)
builder.add_node("inject_feedback", inject_feedback)
builder.add_node("validator", validate_results)
builder.add_node("finalize", finalize)

builder.add_edge("__start__", "seed_detection")
builder.add_edge("seed_detection", "call_model")
builder.add_conditional_edges(
    "call_model",
    route_after_model,
    ["tools", "finalize"],
)
builder.add_edge("tools", "call_model")
builder.add_conditional_edges(
    "validator",
    route_validator,
    ["inject_feedback", "finalize"],
)
builder.add_edge("inject_feedback", "call_model")
builder.add_edge("finalize", "__end__")

permission_detection_graph = builder.compile(name="Required Permission Agent")
