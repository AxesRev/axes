"""Entry point: python -m neo4j_mcp"""

from neo4j_mcp.server.app import mcp
from neo4j_mcp.settings import get_settings


def main() -> None:
    settings = get_settings()
    mcp.run(
        transport="streamable-http",
        host=settings.mcp_host,
        port=settings.mcp_port,
    )


if __name__ == "__main__":
    main()
