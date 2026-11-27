"""Existing graph grant paths for the detected scope or instance."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from examples.react_agent.graph_db import read_graph

logger = logging.getLogger(__name__)

_GRANT_WAYS_QUERY = """
MATCH (rt:Scope {external_id: $scope_external_id})
OPTIONAL MATCH (r:Resource)
WHERE r.external_id IN $resource_external_ids
WITH rt, collect(r) AS resources
WITH [rt] + resources AS targets
UNWIND targets AS target
MATCH (subject)-[hp:HAS_PERMISSION]->(target)
WHERE (subject:Profile OR subject:Group)
  AND coalesce(hp.effect, 'grant') <> 'mute'
  AND (size($permissions) = 0 OR hp.permission IN $permissions)
OPTIONAL MATCH (subject)-[:MEMBER_OF]->(parent_profile:Profile)
WHERE subject:Profile
OPTIONAL MATCH (assigned_group:Group)-[:ASSIGNED_PROFILE]->(subject)
WHERE subject:Profile
WITH target, hp, subject,
     [p IN collect(DISTINCT parent_profile) WHERE p IS NOT NULL | {
         name: p.name,
         external_id: p.external_id
     }] AS parent_profiles,
     [g IN collect(DISTINCT assigned_group) WHERE g IS NOT NULL | {
         name: g.name,
         external_id: g.external_id
     }] AS assigned_groups
RETURN
  CASE WHEN target:Scope THEN 'scope' ELSE 'resource' END AS target_kind,
  target.name AS target_name,
  target.external_id AS target_external_id,
  hp.permission AS permission,
  hp.extra AS extra,
  CASE WHEN subject:Profile THEN 'profile' ELSE 'group' END AS subject_kind,
  subject.name AS subject_name,
  subject.external_id AS subject_external_id,
  parent_profiles,
  assigned_groups
ORDER BY target_kind, target.name, permission, subject_kind, subject.name
"""


@dataclass(frozen=True, slots=True)
class GrantWay:
    target_kind: str
    target_name: str
    target_external_id: str
    permission: str
    extra_note: str
    attach: str
    subject_name: str
    subject_external_id: str
    via: str


def _text(value: Any) -> str:
    return str(value or "").strip()


def _extra_note(extra: Any) -> str:
    payload = extra
    if isinstance(extra, str) and extra.strip():
        try:
            payload = json.loads(extra)
        except json.JSONDecodeError:
            return extra.strip()
    if not isinstance(payload, dict):
        return ""
    access_type = _text(payload.get("access_type"))
    fields = payload.get("fields")
    if access_type == "field" and isinstance(fields, list) and fields:
        names = ", ".join(_text(field) for field in fields if _text(field))
        return f"field ({names})" if names else "field"
    return access_type


def _map_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def parse_grant_way_rows(rows: list[dict[str, Any]]) -> list[GrantWay]:
    ways: list[GrantWay] = []
    seen: set[tuple[str, str, str, str, str]] = set()

    def add(way: GrantWay) -> None:
        key = (way.target_external_id, way.permission, way.attach, way.subject_external_id, way.via)
        if not way.subject_name or not way.subject_external_id or key in seen:
            return
        seen.add(key)
        ways.append(way)

    for row in rows:
        target_kind = _text(row.get("target_kind"))
        target_name = _text(row.get("target_name"))
        target_external_id = _text(row.get("target_external_id"))
        permission = _text(row.get("permission"))
        extra_note = _extra_note(row.get("extra"))
        subject_kind = _text(row.get("subject_kind"))
        subject_name = _text(row.get("subject_name"))
        subject_external_id = _text(row.get("subject_external_id"))
        if not target_kind or not permission or not subject_kind:
            continue
        attach = "assign profile" if subject_kind == "profile" else "add to group"
        add(
            GrantWay(
                target_kind=target_kind,
                target_name=target_name or target_external_id,
                target_external_id=target_external_id,
                permission=permission,
                extra_note=extra_note,
                attach=attach,
                subject_name=subject_name,
                subject_external_id=subject_external_id,
                via="",
            )
        )
        if subject_kind != "profile":
            continue
        for parent in _map_list(row.get("parent_profiles")):
            parent_name = _text(parent.get("name"))
            parent_id = _text(parent.get("external_id"))
            add(
                GrantWay(
                    target_kind=target_kind,
                    target_name=target_name or target_external_id,
                    target_external_id=target_external_id,
                    permission=permission,
                    extra_note=extra_note,
                    attach="assign permission set group",
                    subject_name=parent_name,
                    subject_external_id=parent_id,
                    via=f"contains {subject_name} ({subject_external_id})",
                )
            )
        for group in _map_list(row.get("assigned_groups")):
            group_name = _text(group.get("name"))
            group_id = _text(group.get("external_id"))
            add(
                GrantWay(
                    target_kind=target_kind,
                    target_name=target_name or target_external_id,
                    target_external_id=target_external_id,
                    permission=permission,
                    extra_note=extra_note,
                    attach="add to group",
                    subject_name=group_name,
                    subject_external_id=group_id,
                    via=f"already assigned {subject_name} ({subject_external_id})",
                )
            )
    return ways


def format_grant_ways(ways: list[GrantWay], held_subject_ids: set[str] | None = None) -> str:
    """Render the catalog; ways whose subject the requester already holds are marked as already held."""
    held = held_subject_ids or set()
    if not ways:
        return (
            "Existing ways to add the requested permission:\n"
            "(none found — no profile or group currently holds a matching HAS_PERMISSION "
            "edge on this type or instance)"
        )

    lines = [
        "Existing ways to add the requested permission:",
        "These are the existing HAS_PERMISSION holders. Pick the most fitting of these over creating new grant edges.",
    ]
    current_target = ""
    current_permission = ""
    for way in ways:
        target_label = "scope" if way.target_kind == "scope" else "resource"
        target_key = f"{target_label} {way.target_name} ({way.target_external_id})"
        if target_key != current_target:
            current_target = target_key
            current_permission = ""
            lines.append(f"{target_key}:")
        perm_label = f"{way.permission} ({way.extra_note})" if way.extra_note else way.permission
        if perm_label != current_permission:
            current_permission = perm_label
            lines.append(f"  {perm_label}:")
        via = f" [{way.via}]" if way.via else ""
        already = (
            " [REQUESTER ALREADY HOLDS THIS: they already have this access]" if way.subject_external_id in held else ""
        )
        lines.append(f'    - {way.attach} "{way.subject_name}" ({way.subject_external_id}){via}{already}')
    return "\n".join(lines)


def build_grant_ways_block(catalog: str) -> str:
    stripped = catalog.strip()
    if not stripped:
        return ""
    return f"{stripped}\n\n"


async def fetch_grant_ways(
    *,
    tenant_id: str,
    scope_external_id: str,
    resource_external_ids: list[str],
    permissions: list[str] | None = None,
) -> list[GrantWay]:
    type_id = scope_external_id.strip()
    if not type_id:
        return []

    rows = await read_graph(
        tenant_id,
        _GRANT_WAYS_QUERY,
        {
            "scope_external_id": type_id,
            "resource_external_ids": resource_external_ids,
            "permissions": [name for name in (permissions or []) if name.strip()],
        },
    )
    ways = parse_grant_way_rows(rows)
    logger.info(
        "fetch_grant_ways: type=%s resources=%s rows=%s ways=%s",
        type_id,
        resource_external_ids,
        len(rows),
        len(ways),
    )
    return ways


def grant_way_subject_ids(ways: list[GrantWay]) -> list[str]:
    """Distinct profile/group external ids a user can hold to get the permission."""
    return sorted({way.subject_external_id for way in ways})
