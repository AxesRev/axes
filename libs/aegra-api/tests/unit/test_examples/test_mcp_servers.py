"""Tests for react_agent MCP server URL configuration."""

from __future__ import annotations

import pytest
from examples.react_agent.nodes.tools import _mcp_servers


def test_mcp_servers_uses_trailing_slash_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEO4J_MCP_HOST", "http://127.0.0.1:8811")
    servers = _mcp_servers()
    assert servers["neo4j"]["url"] == "http://127.0.0.1:8811/mcp/"


def test_mcp_servers_normalizes_host_trailing_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEO4J_MCP_HOST", "http://127.0.0.1:8811/")
    servers = _mcp_servers()
    assert servers["neo4j"]["url"] == "http://127.0.0.1:8811/mcp/"
