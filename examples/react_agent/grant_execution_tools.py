"""Per-app tool loaders for the access grant execution subgraph."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.nodes.github_openapi_tools import build_openapi_toolkit
from examples.react_agent.nodes.salesforce_rest_tools import build_salesforce_rest_tools
from examples.react_agent.nodes.tools import _get_all_tools

logger = logging.getLogger(__name__)

AppGrantToolLoader = Callable[[Runtime[Context]], list[Any] | Awaitable[list[Any]]]


def _load_github_grant_tools(runtime: Runtime[Context]) -> list[Any]:
    return build_openapi_toolkit(runtime).get_tools()


async def _load_salesforce_grant_tools(runtime: Runtime[Context]) -> list[Any]:
    return await build_salesforce_rest_tools(runtime)


GRANT_EXECUTION_TOOLS_BY_APP: dict[str, AppGrantToolLoader] = {
    "github": _load_github_grant_tools,
    "salesforce": _load_salesforce_grant_tools,
}


async def load_grant_execution_tools(*, runtime: Runtime[Context], selected_apps: list[str]) -> list[Any]:
    """Load grant-execution tools for each app in ``selected_apps``."""
    tools: list[Any] = []
    loaded_apps: list[str] = []

    for app in selected_apps:
        loader = GRANT_EXECUTION_TOOLS_BY_APP.get(app)
        if loader is None:
            logger.warning("load_grant_execution_tools: no tools registered for app=%s", app)
            continue

        loaded = loader(runtime)
        app_tools = await loaded if inspect.isawaitable(loaded) else loaded
        tools.extend(app_tools)
        loaded_apps.append(app)
        logger.info(
            "load_grant_execution_tools: app=%s tool_count=%d",
            app,
            len(app_tools),
        )

    graph_tools = await _get_all_tools(runtime)
    tools.extend(graph_tools)
    if graph_tools:
        logger.info(
            "load_grant_execution_tools: graph_tool_count=%d graph_tools=%s",
            len(graph_tools),
            [tool.name for tool in graph_tools],
        )

    logger.info(
        "load_grant_execution_tools: selected=%s loaded_apps=%s total_tools=%d",
        selected_apps,
        loaded_apps,
        len(tools),
    )
    return tools
