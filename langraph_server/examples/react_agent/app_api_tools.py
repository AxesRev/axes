"""Per-app GitHub/Salesforce API tools, with read-only vs write access."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.nodes.github_openapi_tools import build_github_api_tools
from examples.react_agent.nodes.salesforce_rest_tools import build_salesforce_rest_tools
from examples.react_agent.nodes.tools import _get_all_tools

logger = logging.getLogger(__name__)

AppApiToolLoader = Callable[..., list[Any] | Awaitable[list[Any]]]


def _load_github_api_tools(
    runtime: Runtime[Context],
    *,
    include_read: bool,
    include_write: bool,
) -> list[Any]:
    return build_github_api_tools(runtime, include_read=include_read, include_write=include_write)


async def _load_salesforce_api_tools(
    runtime: Runtime[Context],
    *,
    include_read: bool,
    include_write: bool,
) -> list[Any]:
    return await build_salesforce_rest_tools(
        runtime,
        include_read=include_read,
        include_write=include_write,
    )


APP_API_TOOLS_BY_APP: dict[str, AppApiToolLoader] = {
    "github": _load_github_api_tools,
    "salesforce": _load_salesforce_api_tools,
}

GRANT_EXECUTION_TOOLS_BY_APP = APP_API_TOOLS_BY_APP


async def load_app_api_tools(
    *,
    runtime: Runtime[Context],
    selected_apps: list[str],
    include_read: bool,
    include_write: bool,
    include_graph: bool = True,
) -> list[Any]:
    """Load app API tools for ``selected_apps``, optionally plus graph/doc tools."""
    tools: list[Any] = []
    loaded_apps: list[str] = []

    for app in selected_apps:
        loader = APP_API_TOOLS_BY_APP.get(app)
        if loader is None:
            logger.warning("load_app_api_tools: no tools registered for app=%s", app)
            continue

        try:
            loaded = loader(runtime, include_read=include_read, include_write=include_write)
            app_tools = await loaded if inspect.isawaitable(loaded) else loaded
        except ValueError:
            logger.warning(
                "load_app_api_tools: skipped app=%s include_read=%s include_write=%s",
                app,
                include_read,
                include_write,
                exc_info=True,
            )
            if include_write:
                raise
            continue

        tools.extend(app_tools)
        loaded_apps.append(app)
        logger.info(
            "load_app_api_tools: app=%s include_read=%s include_write=%s tool_count=%d",
            app,
            include_read,
            include_write,
            len(app_tools),
        )

    if include_graph:
        graph_tools = await _get_all_tools(runtime)
        tools.extend(graph_tools)
        if graph_tools:
            logger.info(
                "load_app_api_tools: graph_tool_count=%d graph_tools=%s",
                len(graph_tools),
                [tool.name for tool in graph_tools],
            )

    logger.info(
        "load_app_api_tools: selected=%s loaded_apps=%s include_read=%s include_write=%s total_tools=%d",
        selected_apps,
        loaded_apps,
        include_read,
        include_write,
        len(tools),
    )
    return tools


async def load_grant_execution_tools(*, runtime: Runtime[Context], selected_apps: list[str]) -> list[Any]:
    """App API tools with write access, plus graph tools."""
    return await load_app_api_tools(
        runtime=runtime,
        selected_apps=selected_apps,
        include_read=True,
        include_write=True,
    )


async def load_detection_lookup_tools(*, runtime: Runtime[Context], selected_apps: list[str]) -> list[Any]:
    """Read-only app API tools (no graph tools; those stay on the detector already)."""
    return await load_app_api_tools(
        runtime=runtime,
        selected_apps=selected_apps,
        include_read=True,
        include_write=False,
        include_graph=False,
    )
