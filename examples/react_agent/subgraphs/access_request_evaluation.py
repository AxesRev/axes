"""Access request evaluation subgraph."""

from __future__ import annotations

import dataclasses
import logging
from typing import Any, cast

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import StateGraph
from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.edges.end import route_model_output
from examples.react_agent.nodes.llm_call import call_model
from examples.react_agent.nodes.tenant_agent_context import load_tenant_agent_context
from examples.react_agent.nodes.tools import execute_tools
from examples.react_agent.prompts import (
    ACCESS_EVALUATION_BASE_PROMPT,
    ACCESS_EVALUATION_EXTRACTOR_PROMPT,
    ACCESS_EVALUATION_TASK_TEMPLATE,
)
from examples.react_agent.state import AccessRequestEvaluation, Permission, State
from examples.react_agent.utils import get_message_text, load_chat_model

logger = logging.getLogger(__name__)


def _seed_evaluation_message(state: State) -> HumanMessage:
    """Build the task message from the detected permission and original user request."""
    user_request = next(
        (get_message_text(message) for message in state.messages if isinstance(message, HumanMessage)), ""
    )
    permission = cast(Permission, state.permission)
    resource_display = permission.resource if permission.resource else "(none — domain-level access)"
    return HumanMessage(
        content=ACCESS_EVALUATION_TASK_TEMPLATE.format(
            user_request=user_request,
            domain=permission.domain,
            resource=resource_display,
            permission_level=permission.permission,
        )
    )


async def seed_evaluation(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Seed the evaluation task from the detected permission and original user request."""
    permission = cast(Permission, state.permission)
    logger.info(
        "seed_evaluation: domain=%r resource=%r permission=%r",
        permission.domain,
        permission.resource,
        permission.permission,
    )
    return {"messages": [_seed_evaluation_message(state)]}


async def call_evaluation_model(state: State, runtime: Runtime[Context]) -> dict[str, list[AIMessage]]:
    """Call the LLM with the access-evaluation system prompt."""
    evaluation_runtime = Runtime(
        context=dataclasses.replace(runtime.context, system_prompt=ACCESS_EVALUATION_BASE_PROMPT),
    )
    return await call_model(state, evaluation_runtime)


async def extract_evaluation(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    model = load_chat_model(runtime.context.model).with_structured_output(AccessRequestEvaluation)
    evaluation = cast(
        AccessRequestEvaluation,
        await model.ainvoke(
            [*state.messages, {"role": "user", "content": ACCESS_EVALUATION_EXTRACTOR_PROMPT}],
        ),
    )
    logger.info("extract_evaluation: should_grant=%s", evaluation.should_grant)
    return {
        "access_evaluation": evaluation,
        "messages": [AIMessage(content=evaluation.model_dump_json())],
    }


builder = StateGraph(State, context_schema=Context)

builder.add_node("load_tenant_agent_context", load_tenant_agent_context)
builder.add_node("seed_evaluation", seed_evaluation)
builder.add_node("call_model", call_evaluation_model)
builder.add_node("tools", execute_tools)
builder.add_node("extract_evaluation", extract_evaluation)

builder.add_edge("__start__", "load_tenant_agent_context")
builder.add_edge("load_tenant_agent_context", "seed_evaluation")
builder.add_edge("seed_evaluation", "call_model")
builder.add_conditional_edges(
    "call_model",
    route_model_output,
    {"tools": "tools", "__end__": "extract_evaluation"},
)
builder.add_edge("tools", "call_model")
builder.add_edge("extract_evaluation", "__end__")

access_request_evaluation_graph = builder.compile(name="Access Request Evaluation")
