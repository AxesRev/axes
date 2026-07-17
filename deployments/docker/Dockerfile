ARG PY_VERSION=3.12
FROM python:${PY_VERSION}-slim-bookworm AS base
ARG PY_VERSION

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

WORKDIR /app

# Create non-root user for runtime
RUN addgroup --system app && adduser --system --ingroup app app

# -----------------------------
# Builder stage
# -----------------------------
FROM base AS builder

# Retrieve the uv binary directly from the official image.
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /bin/uv

# Install system build dependencies required for compiling Python extensions.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy langraph_server package files and workspace lockfile
COPY langraph_server/pyproject.toml langraph_server/README.md ./
COPY uv.lock ./

# Install dependencies from lockfile (includes dev deps for example agents).
RUN uv export --frozen --no-emit-project --format=requirements-txt > requirements.txt && \
    uv pip install --system --compile-bytecode -r requirements.txt && \
    rm requirements.txt

# Copy the actual project source code and forced includes (alembic).
COPY langraph_server/src/ ./src/
COPY langraph_server/alembic.ini ./alembic.ini
COPY langraph_server/alembic/ ./alembic/

# Install the project package itself.
RUN uv pip install --system --compile-bytecode --no-deps .

# -----------------------------
# Final, minimal runtime image
# -----------------------------
FROM base AS final

# Install only minimal runtime libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from the builder stage.
COPY --from=builder /usr/local/lib/python${PY_VERSION}/site-packages/ /usr/local/lib/python${PY_VERSION}/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy runtime assets required by the app and alembic
COPY langraph_server/alembic.ini ./alembic.ini
COPY langraph_server/alembic/ ./alembic/
COPY langraph_server/aegra.json ./aegra.json
COPY langraph_server/examples/ ./examples/

EXPOSE 8000

# Run as non-root
USER app

# Default command - can be overridden by docker-compose
CMD ["uvicorn", "aegra_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
