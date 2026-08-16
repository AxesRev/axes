ARG PY_VERSION=3.12
FROM public.ecr.aws/lambda/python:${PY_VERSION} AS builder
ARG PY_VERSION

COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /usr/local/bin/uv

WORKDIR /build

COPY tenant_service/pyproject.toml ./pyproject.toml
COPY uv.lock ./

RUN uv export --frozen --no-emit-project --no-dev --format=requirements-txt > requirements.txt && \
    uv pip install --system --compile-bytecode -r requirements.txt && \
    rm requirements.txt

FROM public.ecr.aws/lambda/python:${PY_VERSION}
ARG PY_VERSION

COPY --from=builder /var/lang/lib/python${PY_VERSION}/site-packages/ /var/lang/lib/python${PY_VERSION}/site-packages/
COPY --from=builder /var/lang/bin/ /var/lang/bin/

COPY tenant_service/src/tenants ${LAMBDA_TASK_ROOT}/tenants
COPY common ${LAMBDA_TASK_ROOT}/common

CMD ["tenants.app.handler"]
