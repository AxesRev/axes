ARG PY_VERSION=3.12
FROM python:${PY_VERSION}-slim-bookworm AS base
ARG PY_VERSION

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

FROM base AS builder
ARG PY_VERSION

COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /bin/uv

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY pyproject.toml uv.lock ./
COPY billing_service/pyproject.toml billing_service/pyproject.toml
COPY tenant_service/pyproject.toml tenant_service/pyproject.toml
COPY integrations_service/pyproject.toml integrations_service/pyproject.toml
COPY slack_app/pyproject.toml slack_app/pyproject.toml
COPY langraph_server/pyproject.toml langraph_server/README.md langraph_server/
COPY graph_service/pyproject.toml graph_service/pyproject.toml
COPY neo4j_mcp/pyproject.toml neo4j_mcp/pyproject.toml

RUN uv export --frozen --package aegra-slack-app --no-emit-project --no-dev --format=requirements-txt > requirements.txt && \
    uv pip install --system --compile-bytecode -r requirements.txt && \
    rm requirements.txt

FROM base AS final
ARG PY_VERSION

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python${PY_VERSION}/site-packages/ /usr/local/lib/python${PY_VERSION}/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

COPY slack_app/src/slack_app ./slack_app
COPY common ./common

EXPOSE 8000

USER app

CMD ["uvicorn", "slack_app.app:app", "--host", "0.0.0.0", "--port", "8000"]
