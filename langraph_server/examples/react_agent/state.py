"""Define the state structures for the agent."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Annotated

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages
from langgraph.managed import IsLastStep
from pydantic import BaseModel, Field, model_validator

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


class FieldResult(BaseModel):
    """Single-field detection result with the reasoning that produced it."""

    value: Annotated[
        str | None,
        Field(
            description=(
                "Canonical value for this field. For `resource`: if the request is about a specific resource "
                "or named permission object, prefer that entity's identifier from lookup-tool results when "
                "one exists; otherwise the concrete name from the source. If the request is a kind of "
                "permission not tied to a particular instance, use the object/type they mean (or null) — "
                "not an identifier of a related record or neighboring resource."
            ),
        ),
    ] = None
    justification: Annotated[
        str,
        Field(
            description=(
                "1–3 sentences explaining why `value` is correct, grounded in tool results when tools were used; "
                "reject guesswork."
            ),
        ),
    ]


class DetectedPermission(BaseModel):
    """One permission object inside the detector's required-permission list."""

    resource_result: FieldResult
    permission_result: FieldResult
    justification: Annotated[
        str,
        Field(
            min_length=1,
            description=(
                "Proof of why `resource_result.value` is the correct resource (or why it is null). Name the "
                "external data source used: a lookup tool (tool name and the name or identifier it returned), "
                "an injected documentation snippet, or graph/user-context data. The original user request is "
                "not a source. If the request was not about a specific instance, explain why this value is "
                "the permission/object they meant rather than a related record's identifier."
            ),
        ),
    ]


class DetectedPermissionList(BaseModel):
    """Structured detector output: every permission required together for the grant."""

    permissions: Annotated[
        list[DetectedPermission],
        Field(
            min_length=1,
            description=(
                "Permission objects for this grant. Include one object when a single permission is enough. "
                "Include multiple objects only when every one of them is required for the grant: all must be "
                "granted together, and none is an alternative. Do not list mutually exclusive options. Do not "
                "collapse a required set into one broader permission."
            ),
        ),
    ]


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


class ValidationVerdict(BaseModel):
    """Validator's assessment of the per-field results."""

    passed: Annotated[
        bool,
        Field(
            description=(
                "True only if resource and permission together correctly satisfy the user request AND "
                "the detector justification names an external source that proves that choice. "
                "If the request was about a specific resource or named permission object, prefer that "
                "entity's identifier when tools had one. If the request was a kind of permission not tied "
                "to a particular instance, reject a related record/neighbor identifier. "
                "Accept: a justification that cites a lookup tool, documentation snippet, or graph/user-context "
                "record using that same name or identifier. "
                "Reject: guesswork, mismatch with user context, irrelevance, justification contradicting value, "
                "or a justification that only restates the user request."
            ),
        ),
    ]
    resource_feedback: Annotated[
        str | None,
        Field(
            description=(
                "If `passed` is false and `resource` is wrong (including: missing identifier for a specific "
                "entity when tools had one, or a related-record identifier when they asked for a kind of "
                "permission), or the justification does not cite an external source proving that choice: "
                "short note on what was wrong and how to improve (WHAT, not full how-to). Otherwise null."
            )
        ),
    ] = None
    permission_feedback: Annotated[
        str | None,
        Field(
            description=(
                "If `passed` is false and `permission` is wrong: same convention as resource_feedback. Otherwise null."
            )
        ),
    ] = None

    @model_validator(mode="after")
    def _feedback_consistent_with_passed(self) -> ValidationVerdict:
        """Enforce invariants that prompts used to spell out; `with_structured_output` still returns this type."""
        if self.passed:
            if self.resource_feedback is not None or self.permission_feedback is not None:
                msg = "When passed is true, resource_feedback and permission_feedback must be null."
                raise ValueError(msg)
            return self
        feedback_strips = (
            (self.resource_feedback or "").strip(),
            (self.permission_feedback or "").strip(),
        )
        if not any(feedback_strips):
            msg = "When passed is false, at least one feedback field must be a non-empty string."
            raise ValueError(msg)
        return self


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

    detected_permissions: list[DetectedPermission] = field(default_factory=list)
    """Detector items copied from structured output, before they become Permission objects."""

    structured_response: DetectedPermissionList | None = field(default=None)
    """Structured output from the detector agent. Copied into detected_permissions."""

    resource_feedback: str | None = field(default=None)
    """Feedback from the validator when the resource result must be re-derived."""

    permission_feedback: str | None = field(default=None)
    """Feedback from the validator when the permission result must be re-derived."""

    revision_count: int = field(default=0)
    """Number of validator-driven re-run rounds performed so far (capped to bound the loop)."""

    doc_corpus_context: str = field(default="")
    """Semantically retrieved documentation snippets for the current user message (prompt injection)."""

    neo4j_schema: str = field(default="")
    """Neo4j labels, properties, and relationships loaded once per run for Cypher prompts."""

    tenant_agent_context: str = field(default="")
    """Editable tenant-specific instructions loaded from PostgreSQL for access evaluation."""
