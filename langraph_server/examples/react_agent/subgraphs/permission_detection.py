"""Permission detection subgraph."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, NotRequired

from langchain.agents import AgentState, create_agent
from langchain.agents.middleware import AgentMiddleware, ModelRequest, dynamic_prompt
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.graph import StateGraph, add_messages
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.runtime import Runtime

from examples.react_agent.app_api_tools import load_detection_lookup_tools
from examples.react_agent.context import Context
from examples.react_agent.nodes.tools import _get_all_tools
from examples.react_agent.nodes.validator import validate_results
from examples.react_agent.prompts import (
    PERMISSION_DETECTOR_BASE_PROMPT,
    PERMISSION_DETECTOR_FEEDBACK_TEMPLATE,
    PERMISSION_DETECTOR_TASK_TEMPLATE,
)
from examples.react_agent.state import DetectedPermission, Permission, State
from examples.react_agent.user_context_models import UserContextData
from examples.react_agent.user_context_prompt import build_user_context_block
from examples.react_agent.utils import get_message_text, load_chat_model

logger = logging.getLogger(__name__)

MAX_REVISIONS: int = 3

_RESOURCE_DETECTOR_GROUP_LIMIT: int = 20
_RESOURCE_DETECTOR_PROFILE_LIMIT: int = 20
_RESOURCE_DETECTOR_PERMISSION_LIMIT: int = 50


@dataclass
class PermissionDetectionInput:
    """Parent channels this subgraph may read. Transcript stays private."""

    user_request: str = field(default="")
    user_contexts: list[UserContextData] = field(default_factory=list)
    selected_apps: list[str] = field(default_factory=list)
    doc_corpus_context: str = field(default="")


@dataclass
class PermissionDetectionOutput:
    """Typed result plus internal messages for the parent wrapper to filter."""

    permission: Permission | None = field(default=None)
    messages: Annotated[Sequence[AnyMessage], add_messages] = field(default_factory=list)


class PermissionDetectorState(AgentState):
    """create_agent state_schema without managed channels such as is_last_step."""

    user_contexts: NotRequired[list[UserContextData]]
    doc_corpus_context: NotRequired[str]
    selected_apps: NotRequired[list[str]]


def _extra_detector_context(state: State) -> str:
    """Add the user's current group, profile, and resource-access data."""
    if not state.user_contexts:
        return ""

    sections: list[str] = []
    for user_context in state.user_contexts:
        if user_context.groups:
            group_lines = "\n".join(
                group.format_for_context() for group in user_context.groups[:_RESOURCE_DETECTOR_GROUP_LIMIT]
            )
            sections.append(f"Groups this user currently belongs to ({user_context.app}):\n{group_lines}")

        if user_context.profiles:
            profile_lines = "\n".join(
                profile.format_for_context() for profile in user_context.profiles[:_RESOURCE_DETECTOR_PROFILE_LIMIT]
            )
            sections.append(
                f"Profiles and permission sets assigned to this user ({user_context.app}):\n{profile_lines}"
            )

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
    if state.resource_feedback:
        lines.append(f"- resource: {state.resource_feedback}")
    if state.permission_feedback:
        lines.append(f"- permission: {state.permission_feedback}")
    if not lines:
        return ""
    return PERMISSION_DETECTOR_FEEDBACK_TEMPLATE.format(feedback="\n".join(lines))


def _seed(state: State) -> HumanMessage:
    base_content = PERMISSION_DETECTOR_TASK_TEMPLATE.format(
        user_request=state.user_request,
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


def _selected_apps(state: Any) -> list[str]:
    if isinstance(state, dict):
        return list(state.get("selected_apps") or [])
    return list(getattr(state, "selected_apps", None) or [])


async def _inspect_tools_by_name(*, runtime: Any, state: Any) -> dict[str, Any]:
    tools = await load_detection_lookup_tools(
        runtime=runtime,
        selected_apps=_selected_apps(state),
    )
    return {tool.name: tool for tool in tools if getattr(tool, "name", None)}


class _BindDetectorRuntime(AgentMiddleware):
    """Attach inspect-only app API tools at request time and execute them."""

    async def awrap_model_call(self, request: ModelRequest, handler):
        context = request.runtime.context
        inspect_by_name = await _inspect_tools_by_name(runtime=request.runtime, state=request.state)
        existing_names = {getattr(tool, "name", None) for tool in request.tools}
        extra_tools = [tool for name, tool in inspect_by_name.items() if name not in existing_names]
        return await handler(
            request.override(
                model=load_chat_model(
                    context.model,
                    thinking_budget_tokens=context.thinking_budget_tokens,
                    reasoning_effort=context.reasoning_effort,
                ),
                tools=[*request.tools, *extra_tools],
            )
        )

    async def awrap_tool_call(self, request: ToolCallRequest, handler):
        if request.tool is not None:
            return await handler(request)
        inspect_by_name = await _inspect_tools_by_name(runtime=request.runtime, state=request.state)
        tool = inspect_by_name.get(request.tool_call.get("name"))
        if tool is None:
            return await handler(request)
        return await handler(request.override(tool=tool))


async def seed_detection(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    logger.info("seed_detection: starting permission detection")
    return {"messages": [_seed(state)]}


async def apply_structured_response(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    detected = state.structured_response
    if detected is None:
        logger.warning("apply_structured_response: missing structured_response")
        return {}
    logger.info(
        "apply_structured_response: resource=%r permission=%r",
        detected.resource_result.value,
        detected.permission_result.value,
    )
    return {
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

    if state.resource_feedback or state.permission_feedback:
        logger.info("route_validator: feedback present — re-running detector")
        return "inject_feedback"

    logger.info("route_validator: passed — finalize")
    return "finalize"


async def finalize(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    permission_value = state.permission_result.value if state.permission_result else None
    resource_value = state.resource_result.value if state.resource_result else None

    if not permission_value:
        logger.warning("finalize: missing required field(s) — permission=%r", permission_value)
        return {
            "messages": [
                AIMessage(
                    content="Sorry, I could not determine a complete permission for this request (missing required fields)."
                )
            ]
        }

    permission = Permission(resource=resource_value, permission=permission_value)
    logger.info("finalize: resource=%r permission=%r", permission.resource, permission.permission)
    return {"permission": permission}


async def make_permission_detection_graph():
    tools = await _get_all_tools()
    logger.info("permission_detection: %d lookup tool(s): %s", len(tools), [tool.name for tool in tools])
    detector = create_agent(
        model=load_chat_model(Context().model),
        tools=tools,
        system_prompt=PERMISSION_DETECTOR_BASE_PROMPT,
        middleware=[_detector_system_prompt, _BindDetectorRuntime()],
        response_format=ToolStrategy(DetectedPermission),
        state_schema=PermissionDetectorState,
        context_schema=Context,
        name="detector",
    )

    builder = StateGraph(
        State,
        input_schema=PermissionDetectionInput,
        output_schema=PermissionDetectionOutput,
        context_schema=Context,
    )
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


def make_permission_detection_node(compiled):
    """Wrap the detector so only ``permission`` (or a failure reply) reaches the parent."""

    async def run_permission_detection(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
        result = await compiled.ainvoke(state, context=runtime.context)
        permission = result.get("permission")
        if permission is not None:
            return {"permission": permission}
        messages = result.get("messages") or []
        last = messages[-1] if messages else None
        if not isinstance(last, AIMessage) or not get_message_text(last).strip():
            return {}
        return {"messages": [last]}

    return run_permission_detection
