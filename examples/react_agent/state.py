"""Define the state structures for the agent."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Annotated

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages
from langgraph.managed import IsLastStep
from pydantic import BaseModel, Field


class Permission(BaseModel):
    domain: Annotated[str, Field(description="The type of resource to gain access to")]
    resource: Annotated[str | None, Field(description="The name or identifier of the specific resource")] = None
    permission: Annotated[str, Field(description="The name or type of the permission being requested.")]


class FieldResult(BaseModel):
    """Single-field detection result with the reasoning that produced it."""

    value: Annotated[
        str | None,
        Field(description="The detected value for the field. May be null when the field is not applicable."),
    ] = None
    justification: Annotated[
        str,
        Field(description="A short explanation of why this value correctly answers the request."),
    ]


class IntentHints(BaseModel):
    """Per-field hints derived from the user's request.

    Each hint is a clarifying restatement of WHAT the field should describe
    in the user's intent — not HOW to find it.
    """

    domain_hint: Annotated[
        str,
        Field(description="What the `domain` field should describe (the WHAT, not the HOW)."),
    ]
    resource_hint: Annotated[
        str,
        Field(description="What the `resource` field should describe (the WHAT, not the HOW)."),
    ]
    permission_hint: Annotated[
        str,
        Field(description="What the `permission` field should describe (the WHAT, not the HOW)."),
    ]


class ValidationVerdict(BaseModel):
    """Validator's assessment of the per-field results."""

    passed: Annotated[bool, Field(description="True if all three results correctly answer the request.")]
    domain_feedback: Annotated[
        str | None,
        Field(
            description=(
                "Feedback for the domain detector if its result is wrong, explaining what was bad and how "
                "to improve. Must be null when the domain result is correct."
            )
        ),
    ] = None
    resource_feedback: Annotated[
        str | None,
        Field(
            description=(
                "Feedback for the resource detector if its result is wrong. "
                "Must be null when the resource result is correct."
            )
        ),
    ] = None
    permission_feedback: Annotated[
        str | None,
        Field(
            description=(
                "Feedback for the permission detector if its result is wrong. "
                "Must be null when the permission result is correct."
            )
        ),
    ] = None


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

    permission: Permission | None = field(default=None)
    """The structured permission model extracted from the conversation."""

    github_repos: list[str] = field(default_factory=list)
    """Full names (owner/repo) of GitHub repositories accessible to the authenticated user."""

    github_orgs: list[str] = field(default_factory=list)
    """Logins of GitHub organizations the authenticated user belongs to."""

    domain_hint: str | None = field(default=None)
    """Hint describing what the `domain` field should capture (produced by the intent parser)."""

    resource_hint: str | None = field(default=None)
    """Hint describing what the `resource` field should capture (produced by the intent parser)."""

    permission_hint: str | None = field(default=None)
    """Hint describing what the `permission` field should capture (produced by the intent parser)."""

    domain_messages: list[AnyMessage] = field(default_factory=list)
    """Private message thread used by the domain detector loop."""

    resource_messages: list[AnyMessage] = field(default_factory=list)
    """Private message thread used by the resource detector loop."""

    permission_messages: list[AnyMessage] = field(default_factory=list)
    """Private message thread used by the permission detector loop."""

    domain_result: FieldResult | None = field(default=None)
    """Result produced by the domain detector."""

    resource_result: FieldResult | None = field(default=None)
    """Result produced by the resource detector."""

    permission_result: FieldResult | None = field(default=None)
    """Result produced by the permission detector."""

    domain_feedback: str | None = field(default=None)
    """Feedback from the validator when the domain result must be re-derived."""

    resource_feedback: str | None = field(default=None)
    """Feedback from the validator when the resource result must be re-derived."""

    permission_feedback: str | None = field(default=None)
    """Feedback from the validator when the permission result must be re-derived."""

    revision_count: int = field(default=0)
    """Number of validator-driven re-run rounds performed so far (capped to bound the loop)."""
