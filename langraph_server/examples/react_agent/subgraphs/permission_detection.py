"""Permission detection subgraph (Jev). Stage 1: resource type + instance flag."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Annotated, Any

from langchain_core.messages import AIMessage, AnyMessage
from langgraph.graph import StateGraph, add_messages
from langgraph.runtime import Runtime
from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul

from examples.react_agent.context import Context
from examples.react_agent.neo4j_schema_prompt import build_neo4j_schema_block
from examples.react_agent.nodes.tools import read_neo4j_cypher
from examples.react_agent.state import ResourceTypeOption, State
from examples.react_agent.user_context_models import UserContextData
from examples.react_agent.user_context_prompt import build_user_context_block

logger = logging.getLogger(__name__)

JEV_MODEL = "jev-latest"
_CHOICE_OPTION_LIMIT = 255
_NOUL_TRUE_THRESHOLD = 0.5
_CHOICE_ADVANCE_THRESHOLD = 0.5
_RESOURCE_TYPE_INSTRUCTIONS = (
    "Which catalog resource type is this access request about? "
    "Pick the type (Campaign, repository, …), not a record or repo instance."
)
_SPECIFIC_INSTANCE_INSTRUCTIONS = (
    "The user asked for access to a specific named resource instance "
    "(a particular repository, Campaign record, or similar), not only a resource type."
)

_RESOURCE_TYPES_QUERY = """
MATCH (t:Tenant {external_id: $tenant_id})<-[:BELONGS_TO]-(c:AppConnection)
      <-[:BELONGS_TO]-(rt:ResourceType)
WHERE size($apps) = 0 OR c.app IN $apps
RETURN c.app AS app, rt.name AS name, rt.external_id AS external_id
ORDER BY c.app, rt.name
"""


@dataclass
class PermissionDetectionInput:
    """Parent channels this subgraph may read."""

    user_request: str = field(default="")
    user_contexts: list[UserContextData] = field(default_factory=list)
    selected_apps: list[str] = field(default_factory=list)
    doc_corpus_context: str = field(default="")
    neo4j_schema: str = field(default="")


@dataclass
class PermissionDetectionOutput:
    """Stage-1 result. Later Jev stages will extend this."""

    resource_type: str | None = None
    specific_resource_requested: bool = False
    messages: Annotated[Sequence[AnyMessage], add_messages] = field(default_factory=list)


def _jev_api_key() -> str:
    return os.environ.get("JEV_API_KEY", "").strip() or os.environ.get("TYPESAFE_API_KEY", "").strip()


def parse_resource_type_rows(rows: list[dict[str, Any]]) -> list[ResourceTypeOption]:
    options: list[ResourceTypeOption] = []
    seen: set[str] = set()
    for row in rows:
        app = str(row.get("app") or "").strip()
        name = str(row.get("name") or "").strip()
        external_id = str(row.get("external_id") or "").strip()
        if not app or not name or not external_id:
            continue
        if external_id in seen:
            continue
        seen.add(external_id)
        options.append(ResourceTypeOption(app=app, name=name, external_id=external_id))
    return options


@dataclass(frozen=True, slots=True)
class _ChoicePick:
    key: str
    option: ResourceTypeOption
    probability: float


def choice_key(option: ResourceTypeOption, *, name_counts: dict[str, int]) -> str:
    if name_counts.get(option.name, 0) > 1:
        return f"{option.app}:{option.name}"
    return option.name


def keyed_choice_criteria(options: list[ResourceTypeOption]) -> tuple[dict[str, str], dict[str, ResourceTypeOption]]:
    name_counts: dict[str, int] = {}
    app_name_counts: dict[str, int] = {}
    for option in options:
        name_counts[option.name] = name_counts.get(option.name, 0) + 1
        app_name = f"{option.app}:{option.name}"
        app_name_counts[app_name] = app_name_counts.get(app_name, 0) + 1

    criteria: dict[str, str] = {}
    by_key: dict[str, ResourceTypeOption] = {}
    for option in options:
        key = choice_key(option, name_counts=name_counts)
        if key in criteria or app_name_counts.get(f"{option.app}:{option.name}", 0) > 1:
            key = option.external_id
        criteria[key] = f"{option.app} resource type {option.name}"
        by_key[key] = option
    return criteria, by_key


def _chunks(options: list[ResourceTypeOption], size: int) -> list[list[ResourceTypeOption]]:
    return [options[index : index + size] for index in range(0, len(options), size)]


def build_jev_state(state: State) -> str:
    sections = [
        "User access request:",
        state.user_request.strip() or "(empty)",
        "",
        f"Selected apps: {', '.join(state.selected_apps) if state.selected_apps else '(none)'}",
    ]
    user_context = build_user_context_block(state.user_contexts).strip()
    if user_context:
        sections.extend(["", user_context])
    docs = state.doc_corpus_context.strip()
    if docs:
        sections.extend(["", "Documentation snippets:", docs])
    schema = build_neo4j_schema_block(state.neo4j_schema).strip()
    if schema:
        sections.extend(["", schema])
    return "\n".join(sections)


def noul_to_bool(value: float) -> bool:
    return value >= _NOUL_TRUE_THRESHOLD


async def _ask_specific_instance(client: AsyncTypeSafeClient, state_text: str) -> float:
    response = await client.system_one(
        state=state_text,
        questions={
            "specific_resource_requested": Noul(instructions=_SPECIFIC_INSTANCE_INSTRUCTIONS),
        },
    )
    return float(response.nouls["specific_resource_requested"].noul)


async def _choose_resource_type(
    client: AsyncTypeSafeClient,
    state_text: str,
    options: list[ResourceTypeOption],
) -> _ChoicePick | None:
    criteria, by_key = keyed_choice_criteria(options)
    response = await client.system_one(
        state=state_text,
        questions={
            "resource_type": Choice(instructions=_RESOURCE_TYPE_INSTRUCTIONS, criteria=criteria),
        },
    )
    answer = response.choices["resource_type"]
    key = str(answer.choice)
    option = by_key.get(key)
    if option is None:
        logger.warning("resource_type_choice_unknown key=%s options=%s", key, list(by_key))
        return None
    probability = float((answer.probabilities or {}).get(key, 0.0))
    logger.info(
        "resource_type_chunk_choice key=%s probability=%.3f confidence=%s",
        key,
        probability,
        getattr(answer, "confidence", None),
    )
    return _ChoicePick(key=key, option=option, probability=probability)


async def _tournament_resource_type(
    client: AsyncTypeSafeClient,
    state_text: str,
    options: list[ResourceTypeOption],
) -> _ChoicePick | None:
    if not options:
        return None

    chunks = _chunks(options, _CHOICE_OPTION_LIMIT)
    if len(chunks) == 1:
        return await _choose_resource_type(client, state_text, chunks[0])

    picks = await asyncio.gather(*[_choose_resource_type(client, state_text, chunk) for chunk in chunks])
    finalists = [pick for pick in picks if pick is not None and pick.probability > _CHOICE_ADVANCE_THRESHOLD]
    logger.info(
        "resource_type_tournament chunks=%s advanced=%s",
        len(chunks),
        [pick.key for pick in finalists],
    )
    if not finalists:
        return None
    if len(finalists) == 1:
        return finalists[0]
    return await _tournament_resource_type(client, state_text, [pick.option for pick in finalists])


async def load_resource_types(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    tenant_id = runtime.context.tenant_id.strip()
    if not tenant_id:
        logger.warning("load_resource_types: empty tenant_id")
        return {"resource_types": []}

    rows = await read_neo4j_cypher(
        _RESOURCE_TYPES_QUERY,
        {"tenant_id": tenant_id, "apps": list(state.selected_apps)},
    )
    options = parse_resource_type_rows(rows)
    logger.info(
        "load_resource_types: tenant=%s apps=%s count=%s",
        tenant_id,
        state.selected_apps,
        len(options),
    )
    return {"resource_types": options}


def _as_resource_type_options(raw: list[ResourceTypeOption] | list[dict[str, Any]]) -> list[ResourceTypeOption]:
    options: list[ResourceTypeOption] = []
    for item in raw:
        if isinstance(item, ResourceTypeOption):
            options.append(item)
            continue
        parsed = parse_resource_type_rows([item])
        options.extend(parsed)
    return options


async def select_resource_type(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    options = _as_resource_type_options(state.resource_types)
    if not options:
        logger.warning("select_resource_type: no resource types")
        return {"resource_type": None, "specific_resource_requested": False}

    api_key = _jev_api_key()
    if not api_key:
        raise RuntimeError("JEV_API_KEY or TYPESAFE_API_KEY is required for permission detection")

    state_text = build_jev_state(state)
    async with AsyncTypeSafeClient(api_key=api_key, model=JEV_MODEL) as client:
        noul_task = asyncio.create_task(_ask_specific_instance(client, state_text))
        try:
            pick = await _tournament_resource_type(client, state_text, options)
            noul = await noul_task
        finally:
            if not noul_task.done():
                noul_task.cancel()

    resource_type = pick.key if pick is not None else None
    specific = noul_to_bool(noul)
    logger.info(
        "select_resource_type: resource_type=%s specific_resource_requested=%s noul=%.3f",
        resource_type,
        specific,
        noul,
    )
    return {
        "resource_type": resource_type,
        "specific_resource_requested": specific,
        "messages": [
            AIMessage(
                content=json.dumps(
                    {"resource_type": resource_type, "specific_resource_requested": specific},
                    separators=(",", ":"),
                )
            )
        ],
    }


def make_permission_detection_graph():
    builder = StateGraph(
        State,
        input_schema=PermissionDetectionInput,
        output_schema=PermissionDetectionOutput,
        context_schema=Context,
    )
    builder.add_node("load_resource_types", load_resource_types)
    builder.add_node("select_resource_type", select_resource_type)
    builder.add_edge("__start__", "load_resource_types")
    builder.add_edge("load_resource_types", "select_resource_type")
    builder.add_edge("select_resource_type", "__end__")
    return builder.compile(name="Required Permission Agent")


def make_permission_detection_node(compiled):
    """Run stage-1 detection and copy its fields onto the parent state."""

    async def run_permission_detection(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
        result = await compiled.ainvoke(state, context=runtime.context)
        payload = {
            "resource_type": result.get("resource_type"),
            "specific_resource_requested": bool(result.get("specific_resource_requested")),
        }
        messages = result.get("messages") or []
        if not messages:
            messages = [AIMessage(content=json.dumps(payload, separators=(",", ":")))]
        return {**payload, "messages": messages}

    return run_permission_detection
