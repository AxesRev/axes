"""Static response when a request targets unsupported applications."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from examples.react_agent.state import State
from examples.react_agent.supported_apps import UNSUPPORTED_APP_MESSAGE


async def respond_unsupported_app(_state: State) -> dict[str, Any]:
    """End the run with a fixed unsupported-application message."""
    return {"messages": [AIMessage(content=UNSUPPORTED_APP_MESSAGE)]}
