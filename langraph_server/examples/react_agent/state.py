"""Define the state structures for the agent."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Annotated

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages
from langgraph.managed import IsLastStep
from pydantic import BaseModel, Field

from examples.react_agent.user_context_models import UserContextData


class Permission(BaseModel):
    resource: Annotated[
        str | None,
        Field(
            description=(
                "Concrete name or identifier of the entity the request is about, as it appears in tools "
                "(external data sources), documentation, or graph/user-context data. Prefer that entity's "
                "identifier when the request is about a specific resource or named permission object and the "
                "source has one. If the request is a kind of permission not tied to a particular instance, "
                "use the object/type they mean — not a related record's identifier. Null when there is no "
                "such entity."
            ),
        ),
    ] = None
    permission: Annotated[str, Field(description="The name or type of the permission being requested.")]


@dataclass(frozen=True, slots=True)
class ResourceTypeOption:
    """One catalog type for the tenant, from a ResourceType graph node."""

    app: str
    name: str
    external_id: str


def format_detected_permissions(permissions: list[Permission]) -> str:
    """Render the detected permission list for downstream task prompts."""
    lines: list[str] = []
    for permission in permissions:
        resource = permission.resource if permission.resource else "(none — no specific resource)"
        lines.append(f"  - resource: {resource}\n    permission: {permission.permission}")
    return "\n".join(lines)


class AccessRequestEvaluation(BaseModel):
    """Whether a detected permission request should be granted to the user."""

    should_grant: Annotated[
        bool,
        Field(description="True if the requested permission should be granted to the user; false otherwise."),
    ]
    justification: Annotated[
        str,
        Field(
            description=(
                "Past-tense explanation of why this user should or should not receive the requested permissions. "
                "An audit record of that decision, not instructions to a human or LLM. Name only the requested "
                "permissions. Do not add permissions, licenses, features, or user settings, and do not judge "
                "whether that list is enough, complete, or correct. Ground in eligibility and free-text guidelines "
                "(organisation notes, documentation, graph/tool data about who should have these permissions) — "
                "not in whether the user already has the permission, and not in RBAC exact-match rules. Do not "
                "name or describe other users' permissions, roles, or personal data."
            ),
        ),
    ]


@dataclass
class InputState:
    """Defines the input state for the agent, representing a narrower interface to the outside world.

    This class is used to define the initial state and structure of incoming data.
    """

    messages: Annotated[Sequence[AnyMessage], add_messages] = field(default_factory=list)
    """
    Messages tracking the primary execution state of the agent.

    Typically accumulates a pattern of:
    1. HumanMessage - user input
    2. AIMessage with .tool_calls - agent picking tool(s) to use to collect information
    3. ToolMessage(s) - the responses (or errors) from the executed tools
    4. AIMessage without .tool_calls - agent responding in unstructured format to the user
    5. HumanMessage - user responds with the next conversational turn

    Steps 2-5 may repeat as needed.

    The `add_messages` annotation ensures that new messages are merged with existing ones,
    updating by ID to maintain an "append-only" state unless a message with the same ID is provided.
    """


@dataclass
class State(InputState):
    """Represents the complete state of the agent, extending InputState with additional attributes.

    This class can be used to store any information needed throughout the agent's lifecycle.
    """

    is_last_step: IsLastStep = field(default=False)
    """
    Indicates whether the current step is the last one before the graph raises an error.

    This is a 'managed' variable, controlled by the state machine rather than user code.
    It is set to 'True' when the step count reaches recursion_limit - 1.
    """

    permissions: list[Permission] = field(default_factory=list)
    """Permission objects required together for this grant."""

    access_evaluation: AccessRequestEvaluation | None = field(default=None)
    """Evaluation of whether the detected permission request should be granted."""

    selected_apps: list[str] = field(default_factory=list)
    """Supported apps chosen for this request (github, salesforce)."""

    user_contexts: list[UserContextData] = field(default_factory=list)
    """Per-app user, group, and permission context loaded from the graph via Neo4j MCP."""

    user_request: str = field(default="")
    """Original Slack request text. Subgraphs seed from this instead of inheriting parent messages."""

    resource_types: list[ResourceTypeOption] = field(default_factory=list)
    """Tenant catalog of ResourceType nodes for the selected apps."""

    resource_type: str | None = field(default=None)
    """Resource type Jev picked from the catalog (Campaign, repository, …)."""

    specific_resource_requested: bool = field(default=False)
    """True when Jev judged that the user named a specific resource instance."""

    doc_corpus_context: str = field(default="")
    """Semantically retrieved documentation snippets for the current user message (prompt injection)."""

    neo4j_schema: str = field(default="")
    """Neo4j labels, properties, and relationships loaded once per run for Cypher prompts."""

    tenant_agent_context: str = field(default="")
    """Editable tenant-specific instructions loaded from PostgreSQL for access evaluation."""
