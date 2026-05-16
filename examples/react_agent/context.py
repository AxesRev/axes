"""Define the configurable parameters for the agent."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from typing import Annotated

from react_agent import prompts


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
            "description": "GitHub Personal Access Token for GitHub MCP server. Leave empty to disable GitHub tools."
        },
    )

    github_username: str = field(
        default="",
        metadata={
            "description": "GitHub username of the authenticated user. Used to distinguish the current user from the PAT owner."
        },
    )

    github_user_id: str = field(
        default="",
        metadata={
            "description": "GitHub user ID of the authenticated user. Used to distinguish the current user from the PAT owner."
        },
    )

    neo4j_uri: str = field(
        default="",
        metadata={
            "description": (
                "Neo4j Bolt URI for the mcp-neo4j-cypher MCP server (e.g. bolt://localhost:7687). "
                "Leave empty to disable Neo4j tools."
            ),
        },
    )

    neo4j_username: str = field(
        default="",
        metadata={
            "description": "Neo4j username (NEO4J_USERNAME for mcp-neo4j-cypher). Ignored when neo4j_uri is empty.",
        },
    )

    neo4j_password: str = field(
        default="",
        metadata={
            "description": "Neo4j password. Ignored when neo4j_uri is empty.",
        },
    )

    neo4j_database: str = field(
        default="neo4j",
        metadata={"description": "Neo4j database name (NEO4J_DATABASE). Ignored when neo4j_uri is empty."},
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

    def __post_init__(self) -> None:
        """Fetch env vars for attributes that were not passed as args."""
        for f in fields(self):
            if not f.init:
                continue

            if getattr(self, f.name) == f.default:
                raw = os.environ.get(f.name.upper())
                if raw is not None:
                    setattr(self, f.name, type(f.default)(raw))
