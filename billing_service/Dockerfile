ARG PY_VERSION=3.12
FROM public.ecr.aws/lambda/python:${PY_VERSION} AS builder
ARG PY_VERSION

COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /usr/local/bin/uv

WORKDIR /build

COPY langraph_server/pyproject.toml langraph_server/README.md ./
COPY uv.lock ./

RUN uv export --frozen --no-emit-project --format=requirements-txt > requirements.txt && \
    uv pip install --system --compile-bytecode -r requirements.txt && \
    uv pip install --system --compile-bytecode mangum langgraph-sdk && \
    rm requirements.txt

FROM public.ecr.aws/lambda/python:${PY_VERSION}
ARG PY_VERSION

COPY --from=builder /var/lang/lib/python${PY_VERSION}/site-packages/ /var/lang/lib/python${PY_VERSION}/site-packages/
COPY --from=builder /var/lang/bin/ /var/lang/bin/

COPY langraph_server/src/aegra_api ${LAMBDA_TASK_ROOT}/aegra_api
COPY billing_service/src/billing ${LAMBDA_TASK_ROOT}/billing
COPY slack_app ${LAMBDA_TASK_ROOT}/slack_app
COPY tenant ${LAMBDA_TASK_ROOT}/tenant

CMD ["billing.app.handler"]
