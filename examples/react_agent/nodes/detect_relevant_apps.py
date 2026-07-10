"""Classify which supported apps a user request relates to."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from examples.react_agent.context import Context
from examples.react_agent.state import State
from examples.react_agent.supported_apps import APP_DETECTION_MODEL, SUPPORTED_APPS
from examples.react_agent.utils import get_message_text, load_chat_model

logger = logging.getLogger(__name__)


class RelevantAppsSelection(BaseModel):
    apps: list[str] = Field(
        default_factory=list,
        description=(
            "Relevant supported applications mentioned or clearly implied by the user request. "
            "Use only: github, salesforce. Return an empty list when neither applies."
        ),
    )


def _latest_human_message(state: State) -> str:
    for message in reversed(state.messages):
        if isinstance(message, HumanMessage):
            text = get_message_text(message).strip()
            if text:
                return text
    return ""


def normalize_selected_apps(raw_apps: list[str]) -> list[str] | None:
    """Return deduplicated supported apps, or None when selection is invalid."""
    if not raw_apps:
        return None

    normalized: list[str] = []
    for app in raw_apps:
        if app not in SUPPORTED_APPS:
            return None
        if app not in normalized:
            normalized.append(app)
    return normalized or None


async def detect_relevant_apps(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Use a lightweight LLM to choose which supported apps the request targets."""
    user_message = _latest_human_message(state)
    if not user_message:
        logger.info("detect_relevant_apps: empty user message")
        return {"selected_apps": []}

    model = load_chat_model(APP_DETECTION_MODEL).with_structured_output(RelevantAppsSelection)
    selection = await model.ainvoke(
        [
            {
                "role": "system",
                "content": (
                    "You classify access requests by supported application. "
                    "Choose only from: github, salesforce. "
                    "Return one or both when clearly relevant. Return [] when neither applies."
                ),
            },
            {"role": "user", "content": user_message},
        ]
    )
    if not isinstance(selection, RelevantAppsSelection):
        selection = RelevantAppsSelection.model_validate(selection)

    selected_apps = normalize_selected_apps([str(app) for app in selection.apps]) or []
    logger.info("detect_relevant_apps: selected=%s", selected_apps)
    return {"selected_apps": selected_apps}
