"""Pydantic settings for the Neo4j MCP process. Env overrides field defaults."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]


class Neo4jMcpSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_REPO_ROOT / ".env"), str(Path.cwd() / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    NEO4J_URI: str = "bolt://neo4j.neo4j.svc.cluster.local:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_USERNAME: str | None = None
    NEO4J_PASSWORD: str = ""
    NEO4J_DATABASE: str = "neo4j"
    NEO4J_TRANSPORT: str = "http"
    NEO4J_MCP_SERVER_HOST: str = "0.0.0.0"
    NEO4J_MCP_SERVER_PORT: int = 8811
    NEO4J_MCP_SERVER_PATH: str = "/mcp/"
    NEO4J_READ_ONLY: bool = True
    NEO4J_SCHEMA_SAMPLE_SIZE: int = 1000
    NEO4J_MCP_SERVER_ALLOWED_HOSTS: str = (
        "localhost,127.0.0.1,neo4j-mcp,neo4j-mcp.neo4j,neo4j-mcp.neo4j.svc.cluster.local"
    )

    @property
    def username(self) -> str:
        return self.NEO4J_USERNAME or self.NEO4J_USER

    @property
    def allowed_hosts(self) -> list[str]:
        return [host.strip() for host in self.NEO4J_MCP_SERVER_ALLOWED_HOSTS.split(",") if host.strip()]
