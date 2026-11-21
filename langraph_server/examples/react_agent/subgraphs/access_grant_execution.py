"""Access grant execution subgraph."""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Annotated, Any, cast

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.graph import StateGraph, add_messages
from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.edges.end import route_model_output
from examples.react_agent.grant_execution_tools import load_grant_execution_tools
from examples.react_agent.grant_ways import fetch_grant_ways
from examples.react_agent.nodes.llm_call import call_model
from examples.react_agent.nodes.tools import execute_tools
from examples.react_agent.prompts import (
    ACCESS_GRANT_EXECUTION_BASE_PROMPT,
    ACCESS_GRANT_EXECUTION_TASK_TEMPLATE,
)
from examples.react_agent.state import (
    AccessRequestEvaluation,
    ResourceInstanceOption,
    State,
    format_requested_objects,
)
from examples.react_agent.user_context_models import UserContextData
from examples.react_agent.utils import get_message_text

logger = logging.getLogger(__name__)

GRANT_EXECUTION_MODEL = "openai/gpt-5.4-nano"


@dataclass
class AccessGrantInput:
    """Parent channels this subgraph may read. Transcript stays private."""

    user_request: str = field(default="")
    permission_type: str | None = field(default=None)
    access_evaluation: AccessRequestEvaluation | None = field(default=None)
    user_contexts: list[UserContextData] = field(default_factory=list)
    selected_apps: list[str] = field(default_factory=list)
    doc_corpus_context: str = field(default="")
    neo4j_schema: str = field(default="")
    resource_type: str | None = field(default=None)
    resource_type_external_id: str | None = field(default=None)
    requested_objects: list[ResourceInstanceOption] = field(default_factory=list)


@dataclass
class AccessGrantOutput:
    """Internal grant transcript. The parent wrapper copies only the final reply."""

    messages: Annotated[Sequence[AnyMessage], add_messages] = field(default_factory=list)


def _grant_runtime(runtime: Runtime[Context]) -> Runtime[Context]:
    return Runtime(
        context=dataclasses.replace(
            runtime.context,
            system_prompt=ACCESS_GRANT_EXECUTION_BASE_PROMPT,
            model=GRANT_EXECUTION_MODEL,
        ),
    )


def _seed_grant_message(state: State) -> HumanMessage:
    """Build the grant-execution task from the detected target and evaluation."""
    evaluation = cast(AccessRequestEvaluation, state.access_evaluation)
    return HumanMessage(
        content=ACCESS_GRANT_EXECUTION_TASK_TEMPLATE.format(
            user_request=state.user_request,
            resource_type=state.resource_type or "(none)",
            requested_objects=format_requested_objects(state.requested_objects) or "  (none — resource type only)",
            permission_type=state.permission_type or "(none detected — use the grant-ways catalog)",
            evaluation_justification=evaluation.justification,
        )
    )


async def load_grant_ways(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Load existing profile/group grant paths for the detected type or instance."""
    catalog = await fetch_grant_ways(
        resource_type_external_id=state.resource_type_external_id or "",
        resource_external_ids=[obj.external_id for obj in state.requested_objects],
        permissions=[state.permission_type] if state.permission_type else [],
    )
    logger.info(
        "load_grant_ways: type=%s requested_objects=%s chars=%s",
        state.resource_type_external_id,
        [obj.external_id for obj in state.requested_objects],
        len(catalog),
    )
    return {"grant_ways": catalog}


async def seed_grant(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Seed the grant execution task from the detected target and evaluation."""
    evaluation = cast(AccessRequestEvaluation, state.access_evaluation)
    logger.info(
        "seed_grant: type=%s requested_objects=%s should_grant=%s",
        state.resource_type,
        [obj.external_id for obj in state.requested_objects],
        evaluation.should_grant,
    )
    return {"messages": [_seed_grant_message(state)]}


async def call_grant_model(state: State, runtime: Runtime[Context]) -> dict[str, list[Any]]:
    """Call the LLM with grant-execution tools for the selected apps."""
    grant_runtime = _grant_runtime(runtime)
    grant_tools = await load_grant_execution_tools(runtime=grant_runtime, selected_apps=state.selected_apps)
    return await call_model(state, grant_runtime, tools=grant_tools)


async def run_grant_tools(state: State, runtime: Runtime[Context]) -> dict[str, list[Any]]:
    """Execute grant-execution tools for the selected apps."""
    grant_runtime = _grant_runtime(runtime)
    grant_tools = await load_grant_execution_tools(runtime=grant_runtime, selected_apps=state.selected_apps)
    return await execute_tools(state, grant_runtime, tools=grant_tools)


builder = StateGraph(
    State,
    input_schema=AccessGrantInput,
    output_schema=AccessGrantOutput,
    context_schema=Context,
)

builder.add_node("load_grant_ways", load_grant_ways)
builder.add_node("seed_grant", seed_grant)
builder.add_node("call_model", call_grant_model)
builder.add_node("tools", run_grant_tools)

builder.add_edge("__start__", "load_grant_ways")
builder.add_edge("load_grant_ways", "seed_grant")
builder.add_edge("seed_grant", "call_model")
builder.add_conditional_edges(
    "call_model",
    route_model_output,
    {"tools": "tools", "__end__": "__end__"},
)
builder.add_edge("tools", "call_model")

access_grant_execution_graph = builder.compile(name="Access Grant Execution")


async def run_access_grant_execution(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Run grant privately and copy only the final reply to the parent."""
    result = await access_grant_execution_graph.ainvoke(state, context=runtime.context)
    messages = result.get("messages") or []
    last = messages[-1] if messages else None
    if not isinstance(last, AIMessage) or not get_message_text(last).strip():
        return {}
    return {"messages": [last]}
