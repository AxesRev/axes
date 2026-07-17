"""Define the configurable parameters for the agent."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from typing import Annotated

from examples.react_agent import prompts


@dataclass(kw_only=True)
class Context:
    """The context for the agent."""

    system_prompt: str = field(
        default=prompts.SYSTEM_PROMPT,
        metadata={
            "description": "The system prompt to use for the agent's interactions. "
            "This prompt sets the context and behavior for the agent."
        },
    )

    model: Annotated[str, {"__template_metadata__": {"kind": "llm"}}] = field(
        default="openai/gpt-4o-mini",
        metadata={
            "description": "The name of the language model to use for the agent's main interactions. "
            "Should be in the form: provider/model-name."
        },
    )

    max_search_results: int = field(
        default=10,
        metadata={"description": "The maximum number of search results to return for each search query."},
    )

    github_pat: str = field(
        default="",
        metadata={
            "description": (
                "Legacy GitHub PAT setting retained for compatibility. User context is loaded via Neo4j MCP."
            ),
        },
    )

    github_user_id: str = field(
        default="",
        metadata={
            "description": "GitHub user ID of the authenticated user. Used to distinguish the current user from the PAT owner."
        },
    )

    github_email: str = field(
        default="",
        metadata={"description": "Primary verified email from GitHub OAuth for the authenticated Slack user."},
    )

    slack_email: str = field(
        default="",
        metadata={"description": "Primary email from Slack users.info for the message author."},
    )

    github_installation_id: str = field(
        default="",
        metadata={
            "description": (
                "GitHub App installation ID for the org/user. Used to mint installation access tokens for grant execution."
            ),
        },
    )

    tenant_id: str = field(
        default="",
        metadata={"description": "Tenant ID for the Slack workspace. Used to load tenant-specific agent context."},
    )

    reasoning_effort: str = field(
        default="",
        metadata={
            "description": (
                "Reasoning effort for OpenAI reasoning-capable models: 'low', 'medium', or 'high'. "
                "Leave empty to disable (default). Applies to o-series models (openai/o3, openai/o4-mini) "
                "and GPT-5-class models (openai/gpt-5.4-mini, etc.) via the Responses API."
            )
        },
    )

    thinking_budget_tokens: int = field(
        default=0,
        metadata={
            "description": (
                "Token budget for extended thinking. "
                "Applies to Anthropic (claude-3-7-sonnet and newer) and Google Gemini 2.5+. "
                "Set to 0 to disable (default). Anthropic requires the model to be invoked "
                "with max_tokens greater than this value."
            )
        },
    )

    doc_corpus_collection_key: str = field(
        default="default",
        metadata={
            "description": "``collection_key`` for doc corpus search across all apps (env DOC_CORPUS_COLLECTION_KEY).",
        },
    )

    doc_corpus_top_k: int = field(
        default=6,
        metadata={"description": "Max chunks to retrieve per user message (env DOC_CORPUS_TOP_K)."},
    )

    def __post_init__(self) -> None:
        """Fetch env vars for attributes that were not passed as args."""
        for f in fields(self):
            if not f.init:
                continue

            if getattr(self, f.name) == f.default:
                raw = os.environ.get(f.name.upper())
                if raw is not None:
                    setattr(self, f.name, type(f.default)(raw))
