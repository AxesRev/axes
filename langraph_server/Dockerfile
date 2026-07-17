ARG PY_VERSION=3.12
FROM python:${PY_VERSION}-slim-bookworm AS base
ARG PY_VERSION

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

FROM base AS builder

COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /bin/uv

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY langraph_server/pyproject.toml langraph_server/README.md ./
COPY uv.lock ./

RUN uv export --frozen --no-emit-project --format=requirements-txt > requirements.txt && \
    uv pip install --system --compile-bytecode -r requirements.txt && \
    rm requirements.txt

COPY langraph_server/src/ ./src/
COPY langraph_server/alembic.ini ./alembic.ini
COPY langraph_server/alembic/ ./alembic/

RUN uv pip install --system --compile-bytecode --no-deps .

FROM base AS final

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python${PY_VERSION}/site-packages/ /usr/local/lib/python${PY_VERSION}/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

COPY langraph_server/alembic.ini ./alembic.ini
COPY langraph_server/alembic/ ./alembic/
COPY langraph_server/aegra.json ./aegra.json
COPY langraph_server/examples/ ./examples/

EXPOSE 8000

USER app

CMD ["uvicorn", "aegra_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
