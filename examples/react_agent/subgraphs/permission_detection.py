"""Permission detection subgraph."""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import StateGraph
from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.edges.end import route_model_output
from examples.react_agent.nodes.intent_parser import parse_intent
from examples.react_agent.nodes.llm_call import call_model
from examples.react_agent.nodes.tools import execute_tools
from examples.react_agent.nodes.validator import validate_results
from examples.react_agent.prompts import (
    FIELD_DESCRIPTIONS,
    FIELD_DETECTOR_BASE_PROMPT,
    FIELD_DETECTOR_FEEDBACK_TEMPLATE,
    FIELD_DETECTOR_TASK_TEMPLATE,
    FIELD_EXTRACTOR_PROMPT,
)
from examples.react_agent.state import FieldResult, InputState, Permission, State
from examples.react_agent.utils import get_message_text, load_chat_model

logger = logging.getLogger(__name__)

MAX_REVISIONS: int = 3

_FieldName = Literal["domain", "resource", "permission"]

_RESOURCE_DETECTOR_REPO_LIMIT: int = 50
_RESOURCE_DETECTOR_ORG_LIMIT: int = 20


# ---------------------------------------------------------------------------
# Per-field subgraph — reuses call_model, execute_tools, route_model_output
# ---------------------------------------------------------------------------


@dataclass
class FieldDetectionState(State):
    """Extends State with the two fields needed by the per-field subgraph."""

    field_name: _FieldName = "domain"
    result: FieldResult | None = field(default=None)


def _partial_system_prompt(field_name: _FieldName) -> str:
    """Pre-fill {field_name}/{field_description}; leave {github_user_context}/{system_time} for call_model."""

    class _Keep(dict):
        def __missing__(self, key: str) -> str:
            return "{" + key + "}"

    return FIELD_DETECTOR_BASE_PROMPT.format_map(
        _Keep(field_name=field_name, field_description=FIELD_DESCRIPTIONS[field_name])
    )


async def _extract_result(state: FieldDetectionState, runtime: Runtime[Context]) -> dict[str, Any]:
    model = load_chat_model(runtime.context.model).with_structured_output(FieldResult)
    result = cast(
        FieldResult,
        await model.ainvoke(
            [*state.messages, {"role": "user", "content": FIELD_EXTRACTOR_PROMPT.format(field_name=state.field_name)}]
        ),
    )
    logger.info("extract_result[%s]: value=%r", state.field_name, result.value)
    return {"result": result}


_field_builder = StateGraph(FieldDetectionState, context_schema=Context)
_field_builder.add_node("call_model", call_model)
_field_builder.add_node("tools", execute_tools)
_field_builder.add_node("extract_result", _extract_result)
_field_builder.add_edge("__start__", "call_model")
_field_builder.add_conditional_edges(
    "call_model",
    route_model_output,
    {"tools": "tools", "__end__": "extract_result"},
)
_field_builder.add_edge("tools", "call_model")
_field_builder.add_edge("extract_result", "__end__")

_field_detection_graph = _field_builder.compile()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extra_detector_context(state: State, field_name: _FieldName) -> str:
    """Add GitHub repo/org lists to the seeded task when detecting `resource`.

    Keeps concrete owner/repo candidates in the message transcript so resolution does not depend solely on
    system-template placeholders or external graph data.
    """
    if field_name != "resource":
        return ""

    sections: list[str] = []
    if state.github_repos:
        repo_lines = "\n".join(f"- {name}" for name in state.github_repos[:_RESOURCE_DETECTOR_REPO_LIMIT])
        sections.append(
            'Repositories linked to this user (use for vague references like "our test repo"; '
            "prefer an exact owner/repo string):\n" + repo_lines
        )
    if state.github_orgs:
        org_lines = "\n".join(f"- {login}" for login in state.github_orgs[:_RESOURCE_DETECTOR_ORG_LIMIT])
        sections.append("Organizations linked to this user:\n" + org_lines)

    if not sections:
        return ""

    return "\n\n" + "\n\n".join(sections)


def _seed(state: State, field_name: _FieldName, hint: str | None, feedback: str | None) -> HumanMessage:
    user_request = next((get_message_text(m) for m in state.messages if isinstance(m, HumanMessage)), "")
    feedback_block = (
        FIELD_DETECTOR_FEEDBACK_TEMPLATE.format(field_name=field_name, feedback=feedback) if feedback else ""
    )
    base_content = FIELD_DETECTOR_TASK_TEMPLATE.format(
        user_request=user_request,
        field_name=field_name,
        hint=hint or "(no hint — infer from the request)",
        feedback_block=feedback_block,
    )
    return HumanMessage(content=base_content + _extra_detector_context(state, field_name))


async def _detect(
    state: State,
    runtime: Runtime[Context],
    *,
    field_name: _FieldName,
    hint: str | None,
    feedback: str | None,
    result_key: str,
    model: str | None = None,
) -> dict[str, Any]:
    sub_input = FieldDetectionState(
        messages=[_seed(state, field_name, hint, feedback)],
        field_name=field_name,
        github_repos=state.github_repos,
        github_orgs=state.github_orgs,
    )
    field_context = dataclasses.replace(
        runtime.context,
        model=model or runtime.context.model,
        system_prompt=_partial_system_prompt(field_name),
    )
    output = await _field_detection_graph.ainvoke(sub_input, context=field_context)
    return {result_key: output["result"]}


# ---------------------------------------------------------------------------
# Detector nodes
# ---------------------------------------------------------------------------


async def detect_domain(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    return await _detect(
        state,
        runtime,
        field_name="domain",
        hint=state.domain_hint,
        feedback=state.domain_feedback,
        result_key="domain_result",
        model="openai/gpt-5.4-nano",
    )


async def detect_resource(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    return await _detect(
        state,
        runtime,
        field_name="resource",
        hint=state.resource_hint,
        feedback=state.resource_feedback,
        result_key="resource_result",
    )


async def detect_permission(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    return await _detect(
        state,
        runtime,
        field_name="permission",
        hint=state.permission_hint,
        feedback=state.permission_feedback,
        result_key="permission_result",
        model="openai/gpt-5.4-nano",
    )


# ---------------------------------------------------------------------------
# Routing & finalize
# ---------------------------------------------------------------------------


def route_validator(state: State) -> list[str]:
    if state.revision_count >= MAX_REVISIONS:
        logger.warning("route_validator: revision cap (%d) — forcing finalize", state.revision_count)
        return ["finalize"]

    rerun: list[str] = []
    if state.domain_feedback:
        rerun.append("detect_domain")
    if state.resource_feedback:
        rerun.append("detect_resource")
    if state.permission_feedback:
        rerun.append("detect_permission")

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
