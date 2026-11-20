"""Permission detection subgraph (Jev). Stage 1: type, instance flag, optional instance."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Literal

from langchain_core.messages import AIMessage
from langgraph.graph import StateGraph
from langgraph.runtime import Runtime
from typesafe_sdk import AsyncTypeSafeClient, Noul

from examples.react_agent.context import Context
from examples.react_agent.jev_tournament import TournamentOption, jev_choice_tournament
from examples.react_agent.neo4j_schema_prompt import build_neo4j_schema_block
from examples.react_agent.nodes.tools import read_neo4j_cypher
from examples.react_agent.state import ResourceInstanceOption, ResourceTypeOption, State
from examples.react_agent.user_context_models import UserContextData
from examples.react_agent.user_context_prompt import build_user_context_block

logger = logging.getLogger(__name__)

JEV_MODEL = "jev-latest"
_NOUL_TRUE_THRESHOLD = 0.5
_RESOURCE_TYPE_INSTRUCTIONS = (
    "Which catalog resource type is this access request about? "
    "Pick the type (Campaign, repository, …), not a record or repo instance."
)
_RESOURCE_INSTANCE_INSTRUCTIONS = (
    "Which specific resource instance is this access request about? Pick the named record or repository, not the type."
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

_RESOURCE_INSTANCES_QUERY = """
MATCH (t:Tenant {external_id: $tenant_id})<-[:BELONGS_TO]-(c:AppConnection)
      <-[:BELONGS_TO]-(rt:ResourceType {external_id: $resource_type_external_id})
MATCH (r:Resource)-[:INSTANCE_OF]->(rt)
RETURN c.app AS app,
       r.external_id AS external_id,
       r.name AS name,
       r.uri AS uri,
       r.kind AS kind
ORDER BY r.name, r.uri, r.external_id
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
    resource_type_external_id: str | None = None
    specific_resource_requested: bool = False
    requested_objects: list[ResourceInstanceOption] = field(default_factory=list)


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


def parse_resource_instance_rows(rows: list[dict[str, Any]]) -> list[ResourceInstanceOption]:
    options: list[ResourceInstanceOption] = []
    seen: set[str] = set()
    for row in rows:
        external_id = str(row.get("external_id") or "").strip()
        if not external_id or external_id in seen:
            continue
        seen.add(external_id)
        name = str(row.get("name") or "").strip() or external_id
        options.append(
            ResourceInstanceOption(
                app=str(row.get("app") or "").strip(),
                name=name,
                uri=str(row.get("uri") or "").strip(),
                external_id=external_id,
                kind=str(row.get("kind") or "").strip(),
            )
        )
    return options


def resource_type_tournament_option(option: ResourceTypeOption) -> TournamentOption[ResourceTypeOption]:
    return TournamentOption(
        option_id=option.external_id,
        name=option.name,
        description=f"{option.app} resource type {option.name}",
        payload=option,
    )


def resource_instance_tournament_option(
    option: ResourceInstanceOption,
) -> TournamentOption[ResourceInstanceOption]:
    uri = option.uri or option.external_id
    return TournamentOption(
        option_id=option.external_id,
        name=option.name,
        description=f"{option.app} {option.kind or 'resource'} instance {option.name} ({uri})",
        payload=option,
    )


def build_jev_state(state: State) -> str:
    sections = [
        "User access request:",
        state.user_request.strip() or "(empty)",
        "",
        f"Selected apps: {', '.join(state.selected_apps) if state.selected_apps else '(none)'}",
    ]
    if state.resource_type:
        sections.extend(["", f"Selected resource type: {state.resource_type}"])
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


def _as_resource_type_options(raw: list[ResourceTypeOption] | list[dict[str, Any]]) -> list[ResourceTypeOption]:
    options: list[ResourceTypeOption] = []
    for item in raw:
        if isinstance(item, ResourceTypeOption):
            options.append(item)
            continue
        parsed = parse_resource_type_rows([item])
        options.extend(parsed)
    return options


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


async def select_resource_type(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    options = _as_resource_type_options(state.resource_types)
    if not options:
        logger.warning("select_resource_type: no resource types")
        return {
            "resource_type": None,
            "resource_type_external_id": None,
            "specific_resource_requested": False,
        }

    api_key = _jev_api_key()
    if not api_key:
        raise RuntimeError("JEV_API_KEY or TYPESAFE_API_KEY is required for permission detection")

    state_text = build_jev_state(state)
    async with AsyncTypeSafeClient(api_key=api_key, model=JEV_MODEL) as client:
        noul_task = asyncio.create_task(_ask_specific_instance(client, state_text))
        try:
            pick = await jev_choice_tournament(
                client,
                state_text=state_text,
                options=[resource_type_tournament_option(option) for option in options],
                instructions=_RESOURCE_TYPE_INSTRUCTIONS,
                question_id="resource_type",
            )
            noul = await noul_task
        finally:
            if not noul_task.done():
                noul_task.cancel()

    resource_type = pick.key if pick is not None else None
    resource_type_external_id = pick.option.payload.external_id if pick is not None else None
    specific = noul_to_bool(noul)
    logger.info(
        "select_resource_type: resource_type=%s specific_resource_requested=%s noul=%.3f",
        resource_type,
        specific,
        noul,
    )
    return {
        "resource_type": resource_type,
        "resource_type_external_id": resource_type_external_id,
        "specific_resource_requested": specific,
    }


async def select_resource_instance(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    tenant_id = runtime.context.tenant_id.strip()
    type_id = (state.resource_type_external_id or "").strip()
    if not tenant_id or not type_id:
        logger.warning("select_resource_instance: missing tenant or resource type")
        return {"requested_objects": []}

    rows = await read_neo4j_cypher(
        _RESOURCE_INSTANCES_QUERY,
        {"tenant_id": tenant_id, "resource_type_external_id": type_id},
    )
    instances = parse_resource_instance_rows(rows)
    logger.info("select_resource_instance: type=%s count=%s", type_id, len(instances))
    if not instances:
        return {"requested_objects": []}

    api_key = _jev_api_key()
    if not api_key:
        raise RuntimeError("JEV_API_KEY or TYPESAFE_API_KEY is required for permission detection")

    async with AsyncTypeSafeClient(api_key=api_key, model=JEV_MODEL) as client:
        pick = await jev_choice_tournament(
            client,
            state_text=build_jev_state(state),
            options=[resource_instance_tournament_option(instance) for instance in instances],
            instructions=_RESOURCE_INSTANCE_INSTRUCTIONS,
            question_id="resource_instance",
        )

    requested_objects = [pick.option.payload] if pick is not None else []
    logger.info("select_resource_instance: requested_objects=%s", requested_objects)
    return {"requested_objects": requested_objects}


def route_after_select_resource_type(state: State) -> Literal["select_resource_instance", "__end__"]:
    if state.specific_resource_requested and state.resource_type:
        return "select_resource_instance"
    return "__end__"


def make_permission_detection_graph():
    builder = StateGraph(
        State,
        input_schema=PermissionDetectionInput,
        output_schema=PermissionDetectionOutput,
        context_schema=Context,
    )
    builder.add_node("load_resource_types", load_resource_types)
    builder.add_node("select_resource_type", select_resource_type)
    builder.add_node("select_resource_instance", select_resource_instance)
    builder.add_edge("__start__", "load_resource_types")
    builder.add_edge("load_resource_types", "select_resource_type")
    builder.add_conditional_edges(
        "select_resource_type",
        route_after_select_resource_type,
        ["select_resource_instance", "__end__"],
    )
    builder.add_edge("select_resource_instance", "__end__")
    return builder.compile(name="Required Permission Agent")


def make_permission_detection_node(compiled):
    """Run stage-1 detection and copy its fields onto the parent state."""

    async def run_permission_detection(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
        result = await compiled.ainvoke(state, context=runtime.context)
        requested_objects = result["requested_objects"]
        payload = {
            "resource_type": result.get("resource_type"),
            "specific_resource_requested": bool(result.get("specific_resource_requested")),
            "requested_objects": [dataclasses.asdict(obj) for obj in requested_objects],
        }
        return {
            "resource_type": payload["resource_type"],
            "resource_type_external_id": result.get("resource_type_external_id"),
            "requested_objects": requested_objects,
            "messages": [AIMessage(content=json.dumps(payload, separators=(",", ":")))],
        }

    return run_permission_detection
