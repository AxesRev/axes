"""Tests for tenant agent context prompt helpers."""

from examples.react_agent.prompts import ACCESS_EVALUATION_BASE_PROMPT
from examples.react_agent.tenant_agent_context_prompt import build_tenant_agent_context_block


def test_build_tenant_agent_context_block_returns_empty_for_blank_content() -> None:
    assert build_tenant_agent_context_block("") == ""
    assert build_tenant_agent_context_block("   \n  ") == ""


def test_build_tenant_agent_context_block_formats_non_empty_content() -> None:
    block = build_tenant_agent_context_block("Grant read access to contractors.")

    assert "Tenant-specific policy and instructions" in block
    assert "Grant read access to contractors." in block


def test_access_evaluation_prompt_accepts_tenant_context_placeholder() -> None:
    prompt = ACCESS_EVALUATION_BASE_PROMPT.format(
        system_time="2026-07-10T12:00:00+00:00",
        user_context="",
        doc_corpus_context="",
        tenant_agent_context=build_tenant_agent_context_block("Deny admin unless VP approved."),
    )

    assert "Deny admin unless VP approved." in prompt
    assert "Tenant-specific policy and instructions" in prompt
