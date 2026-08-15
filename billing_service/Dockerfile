ARG PY_VERSION=3.12
FROM public.ecr.aws/lambda/python:${PY_VERSION} AS builder
ARG PY_VERSION

COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /usr/local/bin/uv

WORKDIR /build

COPY pyproject.toml uv.lock ./
COPY billing_service/pyproject.toml billing_service/pyproject.toml
COPY tenant_service/pyproject.toml tenant_service/pyproject.toml
COPY integrations_service/pyproject.toml integrations_service/pyproject.toml
COPY langraph_server/pyproject.toml langraph_server/README.md langraph_server/
COPY graph_service/pyproject.toml graph_service/pyproject.toml
COPY neo4j_mcp/pyproject.toml neo4j_mcp/pyproject.toml

RUN uv export --frozen --package aegra-billing-service --no-emit-project --no-dev --format=requirements-txt > requirements.txt && \
    uv pip install --system --compile-bytecode -r requirements.txt && \
    rm requirements.txt

FROM public.ecr.aws/lambda/python:${PY_VERSION}
ARG PY_VERSION

COPY --from=builder /var/lang/lib/python${PY_VERSION}/site-packages/ /var/lang/lib/python${PY_VERSION}/site-packages/
COPY --from=builder /var/lang/bin/ /var/lang/bin/

COPY billing_service/src/billing ${LAMBDA_TASK_ROOT}/billing
COPY common ${LAMBDA_TASK_ROOT}/common

CMD ["billing.app.handler"]
