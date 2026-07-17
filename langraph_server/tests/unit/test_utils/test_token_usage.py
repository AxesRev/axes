"""Unit tests for token usage helpers."""

from aegra_api.utils.token_usage import (
    attach_usage_metadata_callback,
    normalize_usage_metadata,
)


def test_normalize_usage_metadata_preserves_langchain_shape() -> None:
    usage_metadata = {
        "gpt-4o-mini": {
            "input_tokens": 8,
            "output_tokens": 10,
            "total_tokens": 18,
            "input_token_details": {"audio": 0, "cache_read": 0},
            "output_token_details": {"audio": 0, "reasoning": 0},
        },
        "claude-haiku-4-5": {
            "input_tokens": 5,
            "output_tokens": 7,
            "total_tokens": 12,
            "input_token_details": {"cache_read": 0, "cache_creation": 0},
        },
    }

    assert normalize_usage_metadata(usage_metadata) == usage_metadata


def test_normalize_usage_metadata_skips_invalid_entries() -> None:
    usage_metadata = {
        "gpt-4o-mini": {},
        "broken-model": "not-a-dict",
        "valid-model": {"total_tokens": 5},
    }

    assert normalize_usage_metadata(usage_metadata) == {"valid-model": {"total_tokens": 5}}


def test_normalize_usage_metadata_returns_none_when_empty() -> None:
    assert normalize_usage_metadata({}) is None


def test_attach_usage_metadata_callback_preserves_existing_callbacks() -> None:
    existing_callback = object()
    run_config = {"callbacks": [existing_callback]}

    updated_config, callback = attach_usage_metadata_callback(run_config)

    assert updated_config["callbacks"][0] is existing_callback
    assert updated_config["callbacks"][-1] is callback
