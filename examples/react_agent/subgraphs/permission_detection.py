"""Permission detection subgraph."""

from __future__ import annotations

import logging
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

_FieldName = Literal["domain", "resource", "permission"]


def _system_prompt(field_name: _FieldName, state: State, runtime: Runtime[Context]) -> str:
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
        field_name=field_name,
        field_description=FIELD_DESCRIPTIONS[field_name],
        github_user_context=github_user_context,
        system_time=datetime.now(tz=UTC).isoformat(),
    )


def _seed(state: State, field_name: _FieldName, hint: str | None, feedback: str | None) -> HumanMessage:
    user_request = next((get_message_text(m) for m in state.messages if isinstance(m, HumanMessage)), "")
    feedback_block = (
        FIELD_DETECTOR_FEEDBACK_TEMPLATE.format(field_name=field_name, feedback=feedback) if feedback else ""
    )
    return HumanMessage(
        content=FIELD_DETECTOR_TASK_TEMPLATE.format(
            user_request=user_request,
            field_name=field_name,
            hint=hint or "(no hint — infer from the request)",
            feedback_block=feedback_block,
        )
    )


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------


async def call_domain_model(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    messages: list[AnyMessage] = list(state.domain_messages) or [
        _seed(state, "domain", state.domain_hint, state.domain_feedback)
    ]
    tools = await _get_all_tools(runtime)
    model = load_chat_model(
        runtime.context.model,
        thinking_budget_tokens=runtime.context.thinking_budget_tokens,
        reasoning_effort=runtime.context.reasoning_effort,
    ).bind_tools(tools)
    response = await model.ainvoke([{"role": "system", "content": _system_prompt("domain", state, runtime)}, *messages])
    if not isinstance(response, AIMessage):
        raise TypeError(f"Expected AIMessage, got {type(response).__name__}")
    return {"domain_messages": [*messages, response]}


async def domain_tools(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    tools = await _get_all_tools(runtime)
    result = await ToolNode(tools, handle_tool_errors=True).ainvoke({"messages": list(state.domain_messages)})
    return {"domain_messages": [*state.domain_messages, *result["messages"]]}


def route_domain_output(state: State) -> Literal["domain_tools", "extract_domain"]:
    last = state.domain_messages[-1]
    if not isinstance(last, AIMessage):
        raise ValueError(f"Expected AIMessage, got {type(last).__name__}")
    return "domain_tools" if last.tool_calls else "extract_domain"


async def extract_domain(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    model = load_chat_model(runtime.context.model).with_structured_output(FieldResult)
    result = cast(
        FieldResult,
        await model.ainvoke(
            [*state.domain_messages, {"role": "user", "content": FIELD_EXTRACTOR_PROMPT.format(field_name="domain")}]
        ),
    )
    logger.info("extract_domain: value=%r", result.value)
    return {"domain_result": result}


# ---------------------------------------------------------------------------
# Resource
# ---------------------------------------------------------------------------


async def call_resource_model(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    messages: list[AnyMessage] = list(state.resource_messages) or [
        _seed(state, "resource", state.resource_hint, state.resource_feedback)
    ]
    tools = await _get_all_tools(runtime)
    model = load_chat_model(
        runtime.context.model,
        thinking_budget_tokens=runtime.context.thinking_budget_tokens,
        reasoning_effort=runtime.context.reasoning_effort,
    ).bind_tools(tools)
    response = await model.ainvoke(
        [{"role": "system", "content": _system_prompt("resource", state, runtime)}, *messages]
    )
    if not isinstance(response, AIMessage):
        raise TypeError(f"Expected AIMessage, got {type(response).__name__}")
    return {"resource_messages": [*messages, response]}


async def resource_tools(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    tools = await _get_all_tools(runtime)
    result = await ToolNode(tools, handle_tool_errors=True).ainvoke({"messages": list(state.resource_messages)})
    return {"resource_messages": [*state.resource_messages, *result["messages"]]}


def route_resource_output(state: State) -> Literal["resource_tools", "extract_resource"]:
    last = state.resource_messages[-1]
    if not isinstance(last, AIMessage):
        raise ValueError(f"Expected AIMessage, got {type(last).__name__}")
    return "resource_tools" if last.tool_calls else "extract_resource"


async def extract_resource(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    model = load_chat_model(runtime.context.model).with_structured_output(FieldResult)
    result = cast(
        FieldResult,
        await model.ainvoke(
            [
                *state.resource_messages,
                {"role": "user", "content": FIELD_EXTRACTOR_PROMPT.format(field_name="resource")},
            ]
        ),
    )
    logger.info("extract_resource: value=%r", result.value)
    return {"resource_result": result}


# ---------------------------------------------------------------------------
# Permission
# ---------------------------------------------------------------------------


async def call_permission_model(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    messages: list[AnyMessage] = list(state.permission_messages) or [
        _seed(state, "permission", state.permission_hint, state.permission_feedback)
    ]
    tools = await _get_all_tools(runtime)
    model = load_chat_model(
        runtime.context.model,
        thinking_budget_tokens=runtime.context.thinking_budget_tokens,
        reasoning_effort=runtime.context.reasoning_effort,
    ).bind_tools(tools)
    response = await model.ainvoke(
        [{"role": "system", "content": _system_prompt("permission", state, runtime)}, *messages]
    )
    if not isinstance(response, AIMessage):
        raise TypeError(f"Expected AIMessage, got {type(response).__name__}")
    return {"permission_messages": [*messages, response]}


async def permission_tools(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    tools = await _get_all_tools(runtime)
    result = await ToolNode(tools, handle_tool_errors=True).ainvoke({"messages": list(state.permission_messages)})
    return {"permission_messages": [*state.permission_messages, *result["messages"]]}


def route_permission_output(state: State) -> Literal["permission_tools", "extract_permission"]:
    last = state.permission_messages[-1]
    if not isinstance(last, AIMessage):
        raise ValueError(f"Expected AIMessage, got {type(last).__name__}")
    return "permission_tools" if last.tool_calls else "extract_permission"


async def extract_permission(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    model = load_chat_model(runtime.context.model).with_structured_output(FieldResult)
    result = cast(
        FieldResult,
        await model.ainvoke(
            [
                *state.permission_messages,
                {"role": "user", "content": FIELD_EXTRACTOR_PROMPT.format(field_name="permission")},
            ]
        ),
    )
    logger.info("extract_permission: value=%r", result.value)
    return {"permission_result": result}


# ---------------------------------------------------------------------------
# Routing & finalize
# ---------------------------------------------------------------------------


def route_validator(state: State) -> list[str]:
    if state.revision_count >= MAX_REVISIONS:
        logger.warning("route_validator: revision cap (%d) — forcing finalize", state.revision_count)
        return ["finalize"]

    rerun: list[str] = []
    if state.domain_feedback:
        rerun.append("call_domain_model")
    if state.resource_feedback:
        rerun.append("call_resource_model")
    if state.permission_feedback:
        rerun.append("call_permission_model")

    if not rerun:
        logger.info("route_validator: passed — finalize")
        return ["finalize"]

    logger.info("route_validator: re-running %s", rerun)
    return rerun


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

builder.add_node("parse_intent", parse_intent)

builder.add_node("call_domain_model", call_domain_model)
builder.add_node("domain_tools", domain_tools)
builder.add_node("extract_domain", extract_domain)

builder.add_node("call_resource_model", call_resource_model)
builder.add_node("resource_tools", resource_tools)
builder.add_node("extract_resource", extract_resource)

builder.add_node("call_permission_model", call_permission_model)
builder.add_node("permission_tools", permission_tools)
builder.add_node("extract_permission", extract_permission)

builder.add_node("validator", validate_results)
builder.add_node("finalize", finalize)

builder.add_edge("__start__", "parse_intent")

builder.add_edge("parse_intent", "call_domain_model")
builder.add_edge("parse_intent", "call_resource_model")
builder.add_edge("parse_intent", "call_permission_model")

builder.add_conditional_edges("call_domain_model", route_domain_output, ["domain_tools", "extract_domain"])
builder.add_edge("domain_tools", "call_domain_model")
builder.add_edge("extract_domain", "validator")

builder.add_conditional_edges("call_resource_model", route_resource_output, ["resource_tools", "extract_resource"])
builder.add_edge("resource_tools", "call_resource_model")
builder.add_edge("extract_resource", "validator")

builder.add_conditional_edges(
    "call_permission_model", route_permission_output, ["permission_tools", "extract_permission"]
)
builder.add_edge("permission_tools", "call_permission_model")
builder.add_edge("extract_permission", "validator")

builder.add_conditional_edges(
    "validator",
    route_validator,
    ["call_domain_model", "call_resource_model", "call_permission_model", "finalize"],
)

builder.add_edge("finalize", "__end__")

permission_detection_graph = builder.compile(name="Required Permission Agent")
