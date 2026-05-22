"""Access grant execution subgraph."""

from __future__ import annotations

import dataclasses
import logging
from typing import Any, cast

from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph
from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.edges.end import route_model_output
from examples.react_agent.nodes.github_openapi_tools import build_openapi_toolkit
from examples.react_agent.nodes.llm_call import call_model
from examples.react_agent.nodes.tools import execute_tools
from examples.react_agent.prompts import (
    ACCESS_GRANT_EXECUTION_BASE_PROMPT,
    ACCESS_GRANT_EXECUTION_TASK_TEMPLATE,
)
from examples.react_agent.state import AccessRequestEvaluation, Permission, State
from examples.react_agent.utils import get_message_text

logger = logging.getLogger(__name__)


def _seed_grant_message(state: State) -> HumanMessage:
    """Build the grant-execution task from approved permission and evaluation."""
    user_request = next(
        (get_message_text(message) for message in state.messages if isinstance(message, HumanMessage)), ""
    )
    permission = cast(Permission, state.permission)
    evaluation = cast(AccessRequestEvaluation, state.access_evaluation)
    resource_display = permission.resource if permission.resource else "(none — domain-level access)"
    return HumanMessage(
        content=ACCESS_GRANT_EXECUTION_TASK_TEMPLATE.format(
            user_request=user_request,
            domain=permission.domain,
            resource=resource_display,
            permission_level=permission.permission,
            evaluation_justification=evaluation.justification,
        )
    )


async def seed_grant(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Seed the grant execution task from the approved permission request."""
    permission = cast(Permission, state.permission)
    evaluation = cast(AccessRequestEvaluation, state.access_evaluation)
    logger.info(
        "seed_grant: domain=%r resource=%r permission=%r should_grant=%s",
        permission.domain,
        permission.resource,
        permission.permission,
        evaluation.should_grant,
    )
    return {"messages": [_seed_grant_message(state)]}


async def call_grant_model(state: State, runtime: Runtime[Context]) -> dict[str, list[Any]]:
    """Call the LLM with GitHub OpenAPIToolkit tools."""
    grant_runtime = Runtime(
        context=dataclasses.replace(runtime.context, system_prompt=ACCESS_GRANT_EXECUTION_BASE_PROMPT),
    )
    openapi_tools = build_openapi_toolkit(grant_runtime).get_tools()
    return await call_model(state, grant_runtime, tools=openapi_tools)


async def run_grant_tools(state: State, runtime: Runtime[Context]) -> dict[str, list[Any]]:
    """Execute GitHub OpenAPIToolkit tools."""
    openapi_tools = build_openapi_toolkit(runtime).get_tools()
    return await execute_tools(state, runtime, tools=openapi_tools)


builder = StateGraph(State, context_schema=Context)

builder.add_node("seed_grant", seed_grant)
builder.add_node("call_model", call_grant_model)
builder.add_node("tools", run_grant_tools)

builder.add_edge("__start__", "seed_grant")
builder.add_edge("seed_grant", "call_model")
builder.add_conditional_edges(
    "call_model",
    route_model_output,
    {"tools": "tools", "__end__": "__end__"},
)
builder.add_edge("tools", "call_model")

access_grant_execution_graph = builder.compile(name="Access Grant Execution")
