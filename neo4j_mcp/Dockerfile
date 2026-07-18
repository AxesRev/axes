FROM python:3.12-slim-bookworm

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /bin/uv

COPY pyproject.toml ./
COPY src ./src

RUN uv pip install --system --compile-bytecode .

EXPOSE 8811

USER nobody

CMD ["neo4j-mcp-remote"]
