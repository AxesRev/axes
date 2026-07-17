"""Unit tests for Salesforce install state JWT."""

from __future__ import annotations

import jwt as pyjwt
import pytest

from app_integrations.salesforce.install_state import (
    create_salesforce_install_state,
    decode_salesforce_install_state,
)


def test_create_and_decode_install_state_round_trip() -> None:
    state = create_salesforce_install_state(tenant_id="tenant-abc", secret="test-secret")
    assert decode_salesforce_install_state(state, "test-secret") == "tenant-abc"


def test_decode_rejects_wrong_secret() -> None:
    state = create_salesforce_install_state(tenant_id="tenant-abc", secret="test-secret")
    with pytest.raises(pyjwt.PyJWTError):
        decode_salesforce_install_state(state, "other-secret")
