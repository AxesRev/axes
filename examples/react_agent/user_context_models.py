"""User context models built from Neo4j MCP query results."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class UserContextGroup(BaseModel):
    external_id: str
    name: str
    description: str | None = None

    def format_for_context(self) -> str:
        return f"- {self.name} - {self.description}"


class UserContextPermission(BaseModel):
    permission: str
    target_kind: Literal["resource", "group"]
    target_name: str
    target_external_id: str


class UserContextData(BaseModel):
    """User context loaded from the graph for prompt injection and downstream nodes."""

    app: str
    user_id: str
    user_name: str
    groups: list[UserContextGroup] = Field(default_factory=list)
    permissions: list[UserContextPermission] = Field(default_factory=list)

    def format_for_prompt(self) -> str:
        """Render a compact block for LLM system prompts."""
        group_lines = "\n".join(f"  {group.format_for_context()}" for group in self.groups)
        permission_lines = "\n".join(
            f"  - {perm.target_kind} {perm.target_name}: {perm.permission}" for perm in self.permissions
        )
        return (
            "The CURRENT USER you are assisting (loaded from the access graph via Neo4j MCP):\n"
            f"  - App: {self.app}\n"
            f"  - User ID: {self.user_id}\n"
            f"  - Username: {self.user_name}\n\n"
            "Groups this user belongs to:\n"
            f"{group_lines}\n\n"
            "Permissions this user currently has:\n"
            f"{permission_lines}\n\n"
            'Always use this identity when the user refers to "me", "my access", "my repositories", etc.\n'
            "Use this context plus Neo4j tools when facts need verification; do not invent resources or permissions."
        )


def parse_group_rows(rows: list[dict[str, Any]]) -> list[UserContextGroup]:
    groups: list[UserContextGroup] = []
    for row in rows:
        external_id = row.get("external_id")
        name = row.get("name")
        if not external_id or not name:
            continue
        groups.append(
            UserContextGroup(
                external_id=str(external_id),
                name=str(name),
                description=row.get("description"),
            )
        )
    return groups


def parse_permission_rows(rows: list[dict[str, Any]]) -> list[UserContextPermission]:
    permissions: list[UserContextPermission] = []
    for row in rows:
        permission = row.get("permission")
        target_kind = row.get("target_kind")
        target_name = row.get("target_name")
        target_external_id = row.get("target_external_id")
        if not permission or not target_kind or not target_name or not target_external_id:
            continue
        normalized_kind = str(target_kind).lower()
        if normalized_kind not in {"resource", "group"}:
            continue
        permissions.append(
            UserContextPermission(
                permission=str(permission),
                target_kind=normalized_kind,  # type: ignore[arg-type]
                target_name=str(target_name),
                target_external_id=str(target_external_id),
            )
        )
    return permissions


def build_user_context(record: dict[str, Any]) -> UserContextData:
    return UserContextData(
        app=str(record["app"]),
        user_id=str(record["user_id"]),
        user_name=str(record["user_name"]),
        groups=parse_group_rows(record.get("groups") or []),
        permissions=parse_permission_rows(record.get("permissions") or []),
    )
