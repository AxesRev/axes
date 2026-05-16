"""Unit tests for the Settings model."""

import pytest

from neo4j_mcp.settings import Settings


@pytest.mark.unit
def test_settings_defaults() -> None:
    s = Settings()
    assert s.neo4j_uri == "bolt://localhost:7687"
    assert s.neo4j_user == "neo4j"
    assert s.neo4j_database == "neo4j"
    assert s.mcp_port == 8001


@pytest.mark.unit
def test_settings_override_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEO4J_URI", "bolt://my-host:7687")
    monkeypatch.setenv("NEO4J_USER", "admin")

    s = Settings()
    assert s.neo4j_uri == "bolt://my-host:7687"
    assert s.neo4j_user == "admin"
