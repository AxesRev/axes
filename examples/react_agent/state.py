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
    domain: Annotated[str, Field(description="The type of resource to gain access to")]
    resource: Annotated[str | None, Field(description="The name or identifier of the specific resource")] = None
    permission: Annotated[str, Field(description="The name or type of the permission being requested.")]


class FieldResult(BaseModel):
    """Single-field detection result with the reasoning that produced it."""

    value: Annotated[
        str | None,
        Field(
            description=(
                "Canonical value for this field. For `resource`, use null only when the request truly does not "
                "name a specific resource; otherwise use an exact identifier from the target system."
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
                "Natural-language explanation for why the request should or should not be granted, "
                "grounded in tool results and user context when available."
            ),
        ),
    ]


class ValidationVerdict(BaseModel):
    """Validator's assessment of the per-field results."""

    passed: Annotated[
        bool,
        Field(
            description=(
                "True only if domain, resource, and permission together correctly satisfy the user request. "
                "Accept: tool-backed or context-aligned justifications that are logically sound. "
                "Reject: guesswork, mismatch with user context, irrelevance, or justification contradicting value."
            ),
        ),
    ]
    domain_feedback: Annotated[
        str | None,
        Field(
            description=(
                "If `passed` is false and `domain` is wrong: short note on what was wrong and how to improve "
                "(WHAT, not full how-to). Otherwise null."
            )
        ),
    ] = None
    resource_feedback: Annotated[
        str | None,
        Field(
            description=(
                "If `passed` is false and `resource` is wrong: same convention as domain_feedback. Otherwise null."
            )
        ),
    ] = None
    permission_feedback: Annotated[
        str | None,
        Field(
            description=(
                "If `passed` is false and `permission` is wrong: same convention as domain_feedback. Otherwise null."
            )
        ),
    ] = None

    @model_validator(mode="after")
    def _feedback_consistent_with_passed(self) -> ValidationVerdict:
        """Enforce invariants that prompts used to spell out; `with_structured_output` still returns this type."""
        if self.passed:
            if (
                self.domain_feedback is not None
                or self.resource_feedback is not None
                or self.permission_feedback is not None
            ):
                msg = "When passed is true, domain_feedback, resource_feedback, and permission_feedback must be null."
                raise ValueError(msg)
            return self
        feedback_strips = (
            (self.domain_feedback or "").strip(),
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

    permission: Permission | None = field(default=None)
    """The structured permission model extracted from the conversation."""

    access_evaluation: AccessRequestEvaluation | None = field(default=None)
    """Evaluation of whether the detected permission request should be granted."""

    user_context: UserContextData | None = field(default=None)
    """User, group, and permission context loaded from the graph via Neo4j MCP."""

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

    doc_corpus_context: str = field(default="")
    """Semantically retrieved documentation snippets for the current user message (prompt injection)."""
