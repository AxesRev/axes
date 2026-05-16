"""Utility & helper functions."""

from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

# Anthropic requires max_tokens to exceed budget_tokens.
# This headroom leaves room for the text response on top of the thinking budget.
_ANTHROPIC_THINKING_RESPONSE_HEADROOM = 8_000


def get_message_text(msg: BaseMessage) -> str:
    """Get the text content of a message."""
    content = msg.content
    if isinstance(content, str):
        return content
    elif isinstance(content, dict):
        return content.get("text", "")
    else:
        txts = [c if isinstance(c, str) else (c.get("text") or "") for c in content]
        return "".join(txts).strip()


def load_chat_model(
    fully_specified_name: str,
    *,
    thinking_budget_tokens: int = 0,
    reasoning_effort: str = "",
) -> BaseChatModel:
    """Load a chat model from a fully specified name.

    Args:
        fully_specified_name: String in the format 'provider/model'.
        thinking_budget_tokens: Token budget for extended thinking.
            Applies to Anthropic (thinking blocks) and Google Gemini 2.5+
            (thinking_budget). Set to 0 to disable.
        reasoning_effort: Reasoning effort level for OpenAI o-series models
            ("low", "medium", "high"). Ignored for other providers.
    """
    provider, model = fully_specified_name.split("/", maxsplit=1)
    kwargs: dict[str, Any] = {}

    if provider == "anthropic" and thinking_budget_tokens > 0:
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget_tokens}
        kwargs["max_tokens"] = thinking_budget_tokens + _ANTHROPIC_THINKING_RESPONSE_HEADROOM

    elif provider in ("google_genai", "google_vertexai", "google") and thinking_budget_tokens > 0:
        kwargs["thinking_budget"] = thinking_budget_tokens

    elif provider in ("openai", "azure_openai") and reasoning_effort:
        # Use the Responses API semantics (`/v1/responses`) so that reasoning +
        # function tools work together on GPT-5-class models.  Setting `reasoning`
        # instead of `reasoning_effort` causes langchain-openai to route the call
        # through `/v1/responses` automatically.
        kwargs["reasoning"] = {"effort": reasoning_effort}

    return init_chat_model(model, model_provider=provider, **kwargs)
