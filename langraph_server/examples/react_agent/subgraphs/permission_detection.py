"""Permission detection subgraph."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal, NotRequired

from langchain.agents import AgentState, create_agent
from langchain.agents.middleware import ModelRequest, dynamic_prompt, wrap_model_call
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import StateGraph
from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.nodes.tools import _get_all_tools
from examples.react_agent.nodes.validator import validate_results
from examples.react_agent.prompts import (
    PERMISSION_DETECTOR_BASE_PROMPT,
    PERMISSION_DETECTOR_FEEDBACK_TEMPLATE,
    PERMISSION_DETECTOR_TASK_TEMPLATE,
)
from examples.react_agent.state import DetectedPermission, InputState, Permission, State
from examples.react_agent.user_context_models import UserContextData
from examples.react_agent.user_context_prompt import build_user_context_block
from examples.react_agent.utils import get_message_text, load_chat_model

logger = logging.getLogger(__name__)

MAX_REVISIONS: int = 3

_RESOURCE_DETECTOR_GROUP_LIMIT: int = 20
_RESOURCE_DETECTOR_PERMISSION_LIMIT: int = 50


class PermissionDetectorState(AgentState):
    """create_agent state_schema without managed channels such as is_last_step."""

    user_contexts: NotRequired[list[UserContextData]]
    doc_corpus_context: NotRequired[str]


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


@dynamic_prompt
def _detector_system_prompt(request: ModelRequest) -> str:
    state = request.state
    return PERMISSION_DETECTOR_BASE_PROMPT.format(
        system_time=datetime.now(tz=UTC).isoformat(),
        user_context=build_user_context_block(state.get("user_contexts") or []),
        doc_corpus_context=(state.get("doc_corpus_context") or "").strip(),
    )


@wrap_model_call
async def _bind_configured_model(request: ModelRequest, handler):
    context = request.runtime.context
    return await handler(
        request.override(
            model=load_chat_model(
                context.model,
                thinking_budget_tokens=context.thinking_budget_tokens,
                reasoning_effort=context.reasoning_effort,
            )
        )
    )


async def seed_detection(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    logger.info("seed_detection: starting permission detection")
    return {"messages": [_seed(state)]}


async def apply_structured_response(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    detected = state.structured_response
    if detected is None:
        logger.warning("apply_structured_response: missing structured_response")
        return {}
    logger.info(
        "apply_structured_response: domain=%r resource=%r permission=%r",
        detected.domain_result.value,
        detected.resource_result.value,
        detected.permission_result.value,
    )
    return {
        "domain_result": detected.domain_result,
        "resource_result": detected.resource_result,
        "permission_result": detected.permission_result,
    }


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


async def make_permission_detection_graph():
    tools = await _get_all_tools()
    logger.info("permission_detection: %d lookup tool(s): %s", len(tools), [tool.name for tool in tools])
    detector = create_agent(
        model=load_chat_model(Context().model),
        tools=tools,
        system_prompt=PERMISSION_DETECTOR_BASE_PROMPT,
        middleware=[_detector_system_prompt, _bind_configured_model],
        response_format=ToolStrategy(DetectedPermission),
        state_schema=PermissionDetectorState,
        context_schema=Context,
        name="detector",
    )

    builder = StateGraph(State, input_schema=InputState, context_schema=Context)
    builder.add_node("seed_detection", seed_detection)
    builder.add_node("detector", detector)
    builder.add_node("apply_structured_response", apply_structured_response)
    builder.add_node("inject_feedback", inject_feedback)
    builder.add_node("validator", validate_results)
    builder.add_node("finalize", finalize)
    builder.add_edge("__start__", "seed_detection")
    builder.add_edge("seed_detection", "detector")
    builder.add_edge("detector", "apply_structured_response")
    builder.add_edge("apply_structured_response", "validator")
    builder.add_conditional_edges(
        "validator",
        route_validator,
        ["inject_feedback", "finalize"],
    )
    builder.add_edge("inject_feedback", "detector")
    builder.add_edge("finalize", "__end__")
    return builder.compile(name="Required Permission Agent")
