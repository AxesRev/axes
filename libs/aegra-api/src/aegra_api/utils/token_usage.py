"""Helpers for aggregating LLM token usage on runs."""

from typing import Any

from langchain_core.callbacks import UsageMetadataCallbackHandler


def attach_usage_metadata_callback(
    run_config: dict[str, Any],
) -> tuple[dict[str, Any], UsageMetadataCallbackHandler]:
    """Attach LangChain's usage callback to a run config and return the handler."""
    callback = UsageMetadataCallbackHandler()
    callbacks = run_config.get("callbacks", [])
    if not isinstance(callbacks, list):
        callbacks = []
    run_config["callbacks"] = [*callbacks, callback]
    return run_config, callback


def normalize_usage_metadata(usage_metadata: dict[str, Any]) -> dict[str, Any] | None:
    """Return LangChain callback usage metadata keyed by model, or None when empty."""
    if not usage_metadata:
        return None

    normalized: dict[str, Any] = {}
    for model_name, metadata in usage_metadata.items():
        if isinstance(metadata, dict) and metadata:
            normalized[str(model_name)] = metadata

    return normalized or None
