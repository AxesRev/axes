"""Regression tests for react_agent ValidationVerdict invariants."""

from __future__ import annotations

import pytest
from examples.react_agent.state import ValidationVerdict


def test_passed_true_requires_null_feedback() -> None:
    """When passed is true, all feedback fields must be null."""
    ValidationVerdict(passed=True)

    with pytest.raises(ValueError, match="passed is true"):
        ValidationVerdict(passed=True, domain_feedback="fix domain")


def test_passed_false_requires_non_empty_feedback() -> None:
    """When passed is false, at least one feedback string must be non-empty after strip."""
    with pytest.raises(ValueError, match="at least one feedback"):
        ValidationVerdict(passed=False)

    with pytest.raises(ValueError, match="at least one feedback"):
        ValidationVerdict(passed=False, domain_feedback="   ", resource_feedback=None)

    verdict = ValidationVerdict(passed=False, domain_feedback=" adjust domain ")
    assert verdict.domain_feedback == " adjust domain "
