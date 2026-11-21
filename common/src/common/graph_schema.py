"""Access graph schema: vertex types, edge types and the properties ingestion writes.

Ingestion creates these types and indexes in every tenant database, and the agent
shows ``schema_prompt()`` to the LLM so its Cypher uses real labels and properties.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VertexType:
    name: str
    description: str
    properties: tuple[str, ...] = ()


@dataclass(frozen=True)
class EdgeType:
    name: str
    endpoints: tuple[tuple[str, str], ...]
    description: str
    properties: tuple[str, ...] = field(default=())


VERTEX_TYPES: tuple[VertexType, ...] = (
    VertexType("Tenant", "The customer tenant; every AppConnection belongs to it"),
    VertexType("AppConnection", "One connected app instance (a Salesforce org, a GitHub org)", ("extra",)),
    VertexType("ResourceType", "A catalog type (Salesforce object like Account, GitHub repository)"),
    VertexType("Resource", "A concrete record or repository", ("uri", "kind")),
    VertexType("Profile", "Salesforce profile, permission set or permission set group", ("description", "extra")),
    VertexType("Group", "Salesforce role/public group/queue or GitHub team", ("description", "extra")),
    VertexType("AppIdentity", "A user account inside one app", ("kind", "extra")),
    VertexType("Identity", "A person across apps, keyed by lowercased email in external_id", ("kind",)),
)

EDGE_TYPES: tuple[EdgeType, ...] = (
    EdgeType(
        "BELONGS_TO",
        (
            ("AppConnection", "Tenant"),
            ("ResourceType", "AppConnection"),
            ("Resource", "AppConnection"),
            ("Profile", "AppConnection"),
            ("Group", "AppConnection"),
            ("AppIdentity", "AppConnection"),
        ),
        "Ownership: node belongs to its app connection, connection to its tenant",
    ),
    EdgeType("INSTANCE_OF", (("Resource", "ResourceType"),), "A record is an instance of its type"),
    EdgeType(
        "HAS_PERMISSION",
        (
            ("Profile", "ResourceType"),
            ("Group", "Resource"),
            ("AppIdentity", "Resource"),
        ),
        "Access grant; permission is the level, effect is 'grant' or 'mute', extra is JSON text",
        ("permission", "effect", "extra"),
    ),
    EdgeType(
        "MEMBER_OF",
        (("AppIdentity", "Group"), ("Group", "Group"), ("Profile", "Profile")),
        "Membership: user in group, child team in parent team, permission set in permission set group",
    ),
    EdgeType("ASSIGNED_PROFILE", (("AppIdentity", "Profile"), ("Group", "Profile")), "Profile assignment"),
    EdgeType("HAS_PROFILE", (("Identity", "AppIdentity"),), "Person to their app accounts"),
    EdgeType("MANAGER_OF", (("AppIdentity", "AppIdentity"),), "Manager to direct report"),
)


def schema_sql() -> str:
    """Idempotent ArcadeDB ``sqlscript`` creating every type and an external_id index per vertex type.

    Only ``external_id`` is declared (it backs the lookup index); other properties stay
    schemaless so ingestion can write any value type.
    """
    statements: list[str] = []
    for vertex in VERTEX_TYPES:
        statements.append(f"CREATE VERTEX TYPE {vertex.name} IF NOT EXISTS")
        statements.append(f"CREATE PROPERTY {vertex.name}.external_id IF NOT EXISTS STRING")
        statements.append(f"CREATE INDEX IF NOT EXISTS ON {vertex.name} (external_id) NOTUNIQUE")
    statements.extend(f"CREATE EDGE TYPE {edge.name} IF NOT EXISTS" for edge in EDGE_TYPES)
    return ";\n".join(statements) + ";"


def schema_prompt() -> str:
    """Compact schema description for LLM prompts."""
    lines = ["Vertex types (all have app, external_id, name):"]
    for vertex in VERTEX_TYPES:
        extra = f"; also {', '.join(vertex.properties)}" if vertex.properties else ""
        lines.append(f"- {vertex.name}: {vertex.description}{extra}")
    lines.append("Edge types:")
    for edge in EDGE_TYPES:
        shapes = ", ".join(f"({src})-[:{edge.name}]->({dst})" for src, dst in edge.endpoints)
        props = f" Properties: {', '.join(edge.properties)}." if edge.properties else ""
        lines.append(f"- {shapes}. {edge.description}.{props}")
    return "\n".join(lines)
