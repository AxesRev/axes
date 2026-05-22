"""Node that parses the user's access request into per-field hints."""

from __future__ import annotations

import logging
from typing import cast

from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.prompts import INTENT_PARSER_PROMPT
from examples.react_agent.state import IntentHints, State
from examples.react_agent.user_context_prompt import build_user_context_block
from examples.react_agent.utils import load_chat_model

logger = logging.getLogger(__name__)


async def parse_intent(state: State, runtime: Runtime[Context]) -> dict[str, str | None]:
    """Produce per-field hints from the user's access request."""
    if not state.messages:
        raise ValueError("parse_intent: state.messages is empty; an initial user message is required")

    logger.info("Node parse_intent: starting intent parsing (messages in state: %d)", len(state.messages))

    model = load_chat_model(
        "openai/gpt-5.4-mini",
        reasoning_effort="medium",
    ).with_structured_output(IntentHints)

    system_message = INTENT_PARSER_PROMPT.format(
        user_context=build_user_context_block(state.user_context),
        doc_corpus_context=state.doc_corpus_context.strip(),
    )

    response = cast(
        IntentHints,
        await model.ainvoke([{"role": "system", "content": system_message}, *state.messages]),
    )

    logger.info(
        "Node parse_intent: done — domain_hint=%r resource_hint=%r permission_hint=%r",
        response.domain_hint,
        response.resource_hint,
        response.permission_hint,
    )

    return {
        "domain_hint": response.domain_hint,
        "resource_hint": response.resource_hint,
        "permission_hint": response.permission_hint,
    }
