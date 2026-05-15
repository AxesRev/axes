from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Neo4j connection
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    neo4j_database: str = "neo4j"

    # MCP server
    mcp_server_name: str = "neo4j-mcp"
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8001

    # Safety: disallow write queries unless explicitly opted in
    allow_write_queries: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
