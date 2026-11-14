"""Access request evaluation subgraph (Jev)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.graph import StateGraph
from langgraph.runtime import Runtime
from typesafe_sdk import AsyncTypeSafeClient, Noul

from examples.react_agent.context import Context
from examples.react_agent.neo4j_schema_prompt import build_neo4j_schema_block
from examples.react_agent.nodes.tenant_agent_context import load_tenant_agent_context
from examples.react_agent.state import AccessRequestEvaluation, Permission, State, format_detected_permissions
from examples.react_agent.tenant_agent_context_prompt import build_tenant_agent_context_block
from examples.react_agent.user_context_models import UserContextData
from examples.react_agent.user_context_prompt import build_user_context_block

logger = logging.getLogger(__name__)

JEV_MODEL = "jev-latest"
_NOUL_TRUE_THRESHOLD = 0.5
_SHOULD_GRANT_INSTRUCTIONS = (
    "Should the user be granted this permission to this resource/resource type? "
    "If a specific resource instance is named, evaluate that instance; otherwise evaluate the resource type. "
    "The requesting user is the identity in the user-context block. "
    "Decide from organisation guidelines, documentation, role, and org context about who should have this access. "
    "Do not deny because they currently lack the binding, group entitlement, or an RBAC-style rule that already confers it."
)


@dataclass
class AccessEvaluationInput:
    """Parent channels this subgraph may read."""

    user_request: str = field(default="")
    permissions: list[Permission] = field(default_factory=list)
    user_contexts: list[UserContextData] = field(default_factory=list)
    selected_apps: list[str] = field(default_factory=list)
    doc_corpus_context: str = field(default="")
    neo4j_schema: str = field(default="")
    resource_type: str | None = field(default=None)
    resource_type_external_id: str | None = field(default=None)
    specific_resource_requested: bool = field(default=False)
    resource: str | None = field(default=None)
    resource_external_id: str | None = field(default=None)


@dataclass
class AccessEvaluationOutput:
    """Typed decision only. Denial text is added by the parent wrapper."""

    access_evaluation: AccessRequestEvaluation | None = field(default=None)


def _jev_api_key() -> str:
    return os.environ.get("JEV_API_KEY", "").strip() or os.environ.get("TYPESAFE_API_KEY", "").strip()


def _grant_target(state: State) -> str:
    if state.resource:
        return f"resource {state.resource}"
    if state.resource_type:
        return f"resource type {state.resource_type}"
    return "this resource/resource type"


def build_jev_state(state: State) -> str:
    target = _grant_target(state)
    sections = [
        "User access request:",
        state.user_request.strip() or "(empty)",
        "",
        f"Selected apps: {', '.join(state.selected_apps) if state.selected_apps else '(none)'}",
        "",
        "Grant target:",
        f"  resource type: {state.resource_type or '(none)'}",
        f"  resource: {state.resource or '(none — evaluate the resource type)'}",
        f"  evaluate: {target}",
    ]
    if state.permissions:
        sections.extend(["", "Requested permissions:", format_detected_permissions(state.permissions)])
    else:
        sections.append("  permission: (from the user request)")
    user_context = build_user_context_block(state.user_contexts).strip()
    if user_context:
        sections.extend(["", user_context])
    tenant_context = build_tenant_agent_context_block(state.tenant_agent_context).strip()
    if tenant_context:
        sections.extend(["", tenant_context])
    docs = state.doc_corpus_context.strip()
    if docs:
        sections.extend(["", "Documentation snippets:", docs])
    schema = build_neo4j_schema_block(state.neo4j_schema).strip()
    if schema:
        sections.extend(["", schema])
    sections.extend(["", f"System time: {datetime.now(tz=UTC).isoformat()}"])
    return "\n".join(sections)


async def evaluate_access_request(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    api_key = _jev_api_key()
    if not api_key:
        raise RuntimeError("JEV_API_KEY or TYPESAFE_API_KEY is required for access evaluation")

    state_text = build_jev_state(state)
    async with AsyncTypeSafeClient(api_key=api_key, model=JEV_MODEL) as client:
        response = await client.system_one(
            state=state_text,
            questions={"should_grant": Noul(instructions=_SHOULD_GRANT_INSTRUCTIONS)},
        )
    noul = float(response.nouls["should_grant"].noul)
    should_grant = noul >= _NOUL_TRUE_THRESHOLD
    target = _grant_target(state)
    verb = "should" if should_grant else "should not"
    evaluation = AccessRequestEvaluation(
        should_grant=should_grant,
        justification=f"Jev judged that this user {verb} be granted this permission to {target} (noul={noul:.3f}).",
    )
    logger.info("evaluate_access_request: should_grant=%s noul=%.3f target=%s", should_grant, noul, target)
    return {"access_evaluation": evaluation}


builder = StateGraph(
    State,
    input_schema=AccessEvaluationInput,
    output_schema=AccessEvaluationOutput,
    context_schema=Context,
)

builder.add_node("load_tenant_agent_context", load_tenant_agent_context)
builder.add_node("evaluate_access_request", evaluate_access_request)
builder.add_edge("__start__", "load_tenant_agent_context")
builder.add_edge("load_tenant_agent_context", "evaluate_access_request")
builder.add_edge("evaluate_access_request", "__end__")

access_request_evaluation_graph = builder.compile(name="Access Request Evaluation")


async def run_access_request_evaluation(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Run evaluation privately and copy its JSON result onto the parent thread."""
    result = await access_request_evaluation_graph.ainvoke(state, context=runtime.context)
    evaluation = result.get("access_evaluation")
    if evaluation is None:
        return {}
    if isinstance(evaluation, dict):
        evaluation = AccessRequestEvaluation.model_validate(evaluation)
    payload = evaluation.model_dump()
    return {
        "access_evaluation": evaluation,
        "messages": [AIMessage(content=json.dumps(payload, separators=(",", ":")))],
    }
