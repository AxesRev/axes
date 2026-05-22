"""Tests for OpenAPIToolkit factory (access-grant subgraph)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from examples.react_agent.context import Context
from examples.react_agent.nodes import github_openapi_tools as openapi_tools_module
from examples.react_agent.nodes.github_openapi_tools import build_openapi_toolkit


def test_build_openapi_toolkit_requires_installation_id() -> None:
    runtime = MagicMock()
    runtime.context = Context(github_installation_id="")
    with pytest.raises(ValueError, match="github_installation_id"):
        build_openapi_toolkit(runtime)


def test_build_openapi_toolkit_configures_auth_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    openapi_tools_module._toolkit_cache.clear()
    monkeypatch.setenv("GITHUB_API_VERSION", "2022-11-28")
    monkeypatch.setenv("GITHUB_OPENAPI_ALLOW_DANGEROUS_REQUESTS", "true")
    monkeypatch.setattr(
        openapi_tools_module,
        "_load_openapi_dict",
        lambda *, spec_path, spec_url: {"openapi": "3.0.0", "paths": {}},
    )
    monkeypatch.setattr(
        openapi_tools_module,
        "get_installation_access_token",
        lambda installation_id, *, api_version: "ghs_installation_token",
    )

    fake_toolkit = MagicMock()
    with (
        patch.object(openapi_tools_module, "OpenAPIToolkit") as mock_toolkit_cls,
        patch.object(openapi_tools_module, "load_chat_model", return_value=MagicMock()),
    ):
        mock_toolkit_cls.from_llm.return_value = fake_toolkit
        runtime = MagicMock()
        runtime.context = Context(github_installation_id="12345")
        toolkit = build_openapi_toolkit(runtime)

    assert toolkit is fake_toolkit
    call_kwargs = mock_toolkit_cls.from_llm.call_args.kwargs
    assert call_kwargs["allow_dangerous_requests"] is True
    headers = call_kwargs["requests_wrapper"].headers
    assert headers["Authorization"] == "Bearer ghs_installation_token"
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"


def test_build_openapi_toolkit_get_tools_returns_http_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    openapi_tools_module._toolkit_cache.clear()
    monkeypatch.setattr(
        openapi_tools_module,
        "_load_openapi_dict",
        lambda *, spec_path, spec_url: {"openapi": "3.0.0", "paths": {}},
    )
    monkeypatch.setattr(
        openapi_tools_module,
        "get_installation_access_token",
        lambda installation_id, *, api_version: "ghs_installation_token",
    )

    fake_toolkit = MagicMock()
    fake_toolkit.get_tools.return_value = [MagicMock(name="json_explorer"), MagicMock(name="requests_put")]
    with (
        patch.object(openapi_tools_module, "OpenAPIToolkit") as mock_toolkit_cls,
        patch.object(openapi_tools_module, "load_chat_model", return_value=MagicMock()),
    ):
        mock_toolkit_cls.from_llm.return_value = fake_toolkit
        runtime = MagicMock()
        runtime.context = Context(github_installation_id="12345")
        tools = build_openapi_toolkit(runtime).get_tools()

    assert len(tools) == 2
