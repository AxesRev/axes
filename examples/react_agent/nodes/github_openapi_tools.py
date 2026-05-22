"""GitHub REST OpenAPIToolkit factory for the access-grant subgraph."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
from langchain_community.agent_toolkits.openapi.toolkit import OpenAPIToolkit
from langchain_community.tools.json.tool import JsonSpec
from langchain_community.utilities.requests import TextRequestsWrapper
from langgraph.runtime import Runtime

from app_integrations.github.installation_token import get_installation_access_token
from examples.react_agent.context import Context
from examples.react_agent.utils import load_chat_model

logger = logging.getLogger(__name__)

_GITHUB_OPENAPI_SPEC_URL = (
    "https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.json"
)

_toolkit_cache: dict[tuple[Any, ...], OpenAPIToolkit] = {}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _load_openapi_dict(*, spec_path: str, spec_url: str) -> dict[str, Any]:
    if spec_path:
        path = Path(spec_path)
        if not path.is_file():
            msg = f"GITHUB_OPENAPI_SPEC_PATH does not exist: {spec_path}"
            raise FileNotFoundError(msg)
        return json.loads(path.read_text(encoding="utf-8"))

    response = httpx.get(spec_url, timeout=60.0)
    response.raise_for_status()
    loaded = response.json()
    if not isinstance(loaded, dict):
        msg = "GitHub OpenAPI spec must be a JSON object"
        raise TypeError(msg)
    return loaded


def build_openapi_toolkit(runtime: Runtime[Context]) -> OpenAPIToolkit:
    """Build (or return cached) OpenAPIToolkit for GitHub REST API calls."""
    ctx = runtime.context
    installation_id = ctx.github_installation_id.strip()
    if not installation_id:
        msg = "github_installation_id is required for GitHub API tools"
        raise ValueError(msg)

    spec_path = os.environ.get("GITHUB_OPENAPI_SPEC_PATH", "").strip()
    api_version = os.environ.get("GITHUB_API_VERSION", "2022-11-28").strip()
    allow_dangerous = _env_bool("GITHUB_OPENAPI_ALLOW_DANGEROUS_REQUESTS", True)
    json_agent_max_iterations = int(os.environ.get("GITHUB_OPENAPI_JSON_AGENT_MAX_ITERATIONS", "15"))
    json_spec_max_value_length = int(os.environ.get("GITHUB_OPENAPI_JSON_SPEC_MAX_VALUE_LENGTH", "200"))
    verbose = _env_bool("GITHUB_OPENAPI_VERBOSE", False)
    access_token = get_installation_access_token(installation_id, api_version=api_version)

    cache_key = (
        ctx.model,
        installation_id,
        access_token,
        spec_path,
        api_version,
        allow_dangerous,
        json_agent_max_iterations,
        json_spec_max_value_length,
        verbose,
    )
    cached = _toolkit_cache.get(cache_key)
    if cached is not None:
        return cached

    openapi_dict = _load_openapi_dict(spec_path=spec_path, spec_url=_GITHUB_OPENAPI_SPEC_URL)
    llm = load_chat_model(
        ctx.model,
        thinking_budget_tokens=ctx.thinking_budget_tokens,
        reasoning_effort=ctx.reasoning_effort,
    )
    requests_wrapper = TextRequestsWrapper(
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-GitHub-Api-Version": api_version,
            "Accept": "application/vnd.github+json",
        },
    )
    toolkit = OpenAPIToolkit.from_llm(
        llm=llm,
        json_spec=JsonSpec(dict_=openapi_dict, max_value_length=json_spec_max_value_length),
        requests_wrapper=requests_wrapper,
        allow_dangerous_requests=allow_dangerous,
        verbose=verbose,
        agent_executor_kwargs={"max_iterations": json_agent_max_iterations},
    )
    _toolkit_cache[cache_key] = toolkit
    logger.info(
        "github_openapi_toolkit: initialized (spec=%s, api_version=%s, allow_dangerous=%s)",
        spec_path or _GITHUB_OPENAPI_SPEC_URL,
        api_version,
        allow_dangerous,
    )
    return toolkit
