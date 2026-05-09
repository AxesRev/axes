"""Validator node for the permission detection subgraph.

Reads the original user request and the three per-field results, then asks an
LLM to produce a structured verdict that says either "all good" or which
fields need to be re-derived (with feedback).
"""

from __future__ import annotations

import json
import logging
from typing import Any, cast

from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.prompts import VALIDATOR_PROMPT
from examples.react_agent.state import FieldResult, State, ValidationVerdict
from examples.react_agent.utils import get_message_text, load_chat_model

logger = logging.getLogger(__name__)


def _extract_user_request(state: State) -> str:
    """Return the text of the first HumanMessage in state.messages."""
    for message in state.messages:
        if isinstance(message, HumanMessage):
            return get_message_text(message)
    raise ValueError("validator: no HumanMessage found in state.messages")


def _serialize_field(result: FieldResult | None) -> dict[str, Any]:
    if result is None:
        return {"value": None, "justification": "(no result produced)"}
    return {"value": result.value, "justification": result.justification}


async def validate_results(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Validate the three per-field results and return per-field feedback (or pass).

    Always returns updates for `domain_feedback`, `resource_feedback`,
    `permission_feedback`, and `revision_count` so stale feedback from a
    previous round is cleared on every validator turn.
    """
    user_request = _extract_user_request(state)
    payload = {
        "user_request": user_request,
        "results": {
            "domain": _serialize_field(state.domain_result),
            "resource": _serialize_field(state.resource_result),
            "permission": _serialize_field(state.permission_result),
        },
    }

    logger.info(
        "Node validator: starting (revision=%d) domain=%r resource=%r permission=%r",
        state.revision_count,
        state.domain_result.value if state.domain_result else None,
        state.resource_result.value if state.resource_result else None,
        state.permission_result.value if state.permission_result else None,
    )

    model = load_chat_model(runtime.context.model).with_structured_output(ValidationVerdict)
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
        logger.info("Node validator: passed — all three fields accepted")
        return {
            "domain_feedback": None,
            "resource_feedback": None,
            "permission_feedback": None,
            "revision_count": state.revision_count + 1,
        }

    logger.info(
        "Node validator: failed — domain_fb=%s resource_fb=%s permission_fb=%s",
        bool(verdict.domain_feedback),
        bool(verdict.resource_feedback),
        bool(verdict.permission_feedback),
    )
    update: dict[str, Any] = {
        "domain_feedback": verdict.domain_feedback,
        "resource_feedback": verdict.resource_feedback,
        "permission_feedback": verdict.permission_feedback,
        "revision_count": state.revision_count + 1,
    }
    # Clear the message thread for every field that needs a fresh re-run.
    if verdict.domain_feedback:
        update["domain_messages"] = []
    if verdict.resource_feedback:
        update["resource_messages"] = []
    if verdict.permission_feedback:
        update["permission_messages"] = []
    return update
