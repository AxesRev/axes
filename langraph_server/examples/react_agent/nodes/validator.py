"""Validator node for the permission detection subgraph.

Reads the original user request, the two per-field results, and the detector
justification, then asks an LLM to produce a structured verdict that says
either "all good" or which fields need to be re-derived (with feedback).
"""

from __future__ import annotations

import json
import logging
from typing import Any, cast

from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.prompts import VALIDATOR_PROMPT
from examples.react_agent.state import FieldResult, State, ValidationVerdict
from examples.react_agent.utils import load_chat_model

logger = logging.getLogger(__name__)


def _extract_user_request(state: State) -> str:
    user_request = state.user_request.strip()
    if not user_request:
        raise ValueError("validator: user_request is empty")
    return user_request


def _serialize_field(result: FieldResult | None) -> dict[str, Any]:
    if result is None:
        return {"value": None, "justification": "(no result produced)"}
    return {"value": result.value, "justification": result.justification}


async def validate_results(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Validate the two per-field results and return per-field feedback (or pass).

    Always returns updates for `resource_feedback`, `permission_feedback`,
    and `revision_count` so stale feedback from a previous round is cleared
    on every validator turn.
    """
    user_request = _extract_user_request(state)
    payload = {
        "user_request": user_request,
        "permissions": [
            {
                "resource": _serialize_field(item.resource_result),
                "permission": _serialize_field(item.permission_result),
                "justification": item.justification,
            }
            for item in state.detected_permissions
        ],
    }

    logger.info(
        "Node validator: starting (revision=%d) permissions=%s",
        state.revision_count,
        [(item.resource_result.value, item.permission_result.value) for item in state.detected_permissions],
    )

    model = load_chat_model(
        runtime.context.model,
        thinking_budget_tokens=runtime.context.thinking_budget_tokens,
        reasoning_effort=runtime.context.reasoning_effort,
    ).with_structured_output(ValidationVerdict)
    verdict = cast(
        ValidationVerdict,
        await model.ainvoke(
            [
                {"role": "system", "content": VALIDATOR_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
            ]
        ),
    )

    if verdict.passed:
        logger.info("Node validator: passed — both fields accepted")
        return {
            "resource_feedback": None,
            "permission_feedback": None,
            "revision_count": state.revision_count + 1,
        }

    logger.info(
        "Node validator: failed — resource_fb=%s permission_fb=%s",
        bool(verdict.resource_feedback),
        bool(verdict.permission_feedback),
    )
    return {
        "resource_feedback": verdict.resource_feedback,
        "permission_feedback": verdict.permission_feedback,
        "revision_count": state.revision_count + 1,
    }
