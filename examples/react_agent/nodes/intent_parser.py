"""Node that parses the user's access request into per-field hints.

This is the first node in the new permission detection subgraph: it reads the
incoming user message and produces one short hint per output field
(`domain`, `resource`, `permission`) that the downstream per-field detectors
can each use as their goal description.
"""

from __future__ import annotations

import logging
from typing import cast

from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.prompts import GITHUB_USER_CONTEXT, INTENT_PARSER_PROMPT
from examples.react_agent.state import IntentHints, State
from examples.react_agent.utils import load_chat_model

logger = logging.getLogger(__name__)


def _build_github_user_context(state: State, runtime: Runtime[Context]) -> str:
    """Render the optional GitHub user-context block (matches `call_model`'s formatting)."""
    if not runtime.context.github_username:
        return ""
    return GITHUB_USER_CONTEXT.format(
        github_username=runtime.context.github_username,
        github_user_id=runtime.context.github_user_id,
        github_repos=", ".join(state.github_repos) if state.github_repos else "none",
        github_orgs=", ".join(state.github_orgs) if state.github_orgs else "none",
    )


async def parse_intent(state: State, runtime: Runtime[Context]) -> dict[str, str | None]:
    """Produce per-field hints from the user's access request.

    Returns a partial state update with `domain_hint`, `resource_hint`,
    `permission_hint`. Each hint clarifies WHAT the corresponding field
    should describe — never HOW to obtain it.
    """
    if not state.messages:
        raise ValueError("parse_intent: state.messages is empty; an initial user message is required")

    logger.info("Node parse_intent: starting intent parsing (messages in state: %d)", len(state.messages))

    model = load_chat_model(
        "openai/gpt-5.4-mini",
        reasoning_effort="medium",
    ).with_structured_output(IntentHints)

    system_message = INTENT_PARSER_PROMPT.format(
        github_user_context=_build_github_user_context(state, runtime),
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
