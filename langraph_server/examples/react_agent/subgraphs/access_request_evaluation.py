"""Access request evaluation subgraph."""

from __future__ import annotations

import dataclasses
import json
import logging
from dataclasses import dataclass, field
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
from examples.react_agent.state import (
    AccessRequestEvaluation,
    ResourceInstanceOption,
    State,
    format_requested_objects,
)
from examples.react_agent.user_context_models import UserContextData
from examples.react_agent.utils import load_chat_model

logger = logging.getLogger(__name__)


@dataclass
class AccessEvaluationInput:
    """Parent channels this subgraph may read. Transcript stays private."""

    user_request: str = field(default="")
    permission_type: str | None = field(default=None)
    user_contexts: list[UserContextData] = field(default_factory=list)
    selected_apps: list[str] = field(default_factory=list)
    doc_corpus_context: str = field(default="")
    graph_schema: str = field(default="")
    resource_type: str | None = field(default=None)
    requested_objects: list[ResourceInstanceOption] = field(default_factory=list)


@dataclass
class AccessEvaluationOutput:
    """Typed decision only. Denial text is added by the parent wrapper."""

    access_evaluation: AccessRequestEvaluation | None = field(default=None)


def _seed_evaluation_message(state: State) -> HumanMessage:
    """Build the task message from the detected target and original user request."""
    return HumanMessage(
        content=ACCESS_EVALUATION_TASK_TEMPLATE.format(
            user_request=state.user_request,
            resource_type=state.resource_type or "(none)",
            requested_objects=format_requested_objects(state.requested_objects)
            or "  (none — evaluate the resource type)",
            permission_type=state.permission_type or "(none detected — evaluate the resource/resource type)",
        )
    )


async def seed_evaluation(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Seed the evaluation task from the detected target and original user request."""
    logger.info(
        "seed_evaluation: type=%s requested_objects=%s permission_type=%s",
        state.resource_type,
        [obj.external_id for obj in state.requested_objects],
        state.permission_type,
    )
    return {"messages": [_seed_evaluation_message(state)]}


async def call_evaluation_model(state: State, runtime: Runtime[Context]) -> dict[str, list[AIMessage]]:
    """Call the LLM with the access-evaluation system prompt."""
    evaluation_runtime = Runtime(
        context=dataclasses.replace(runtime.context, system_prompt=ACCESS_EVALUATION_BASE_PROMPT),
    )
    return await call_model(state, evaluation_runtime)


async def extract_evaluation(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    model = load_chat_model(
        runtime.context.model,
        thinking_budget_tokens=runtime.context.thinking_budget_tokens,
        reasoning_effort=runtime.context.reasoning_effort,
    ).with_structured_output(AccessRequestEvaluation)
    evaluation = cast(
        AccessRequestEvaluation,
        await model.ainvoke(
            [*state.messages, {"role": "user", "content": ACCESS_EVALUATION_EXTRACTOR_PROMPT}],
        ),
    )
    logger.info("extract_evaluation: should_grant=%s", evaluation.should_grant)
    return {"access_evaluation": evaluation}


builder = StateGraph(
    State,
    input_schema=AccessEvaluationInput,
    output_schema=AccessEvaluationOutput,
    context_schema=Context,
)

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
