"""Supported application identifiers for access-request routing."""

from __future__ import annotations

from typing import Literal

SupportedApp = Literal["github", "salesforce"]

SUPPORTED_APPS: frozenset[str] = frozenset({"github", "salesforce"})

UNSUPPORTED_APP_MESSAGE = "sorry this application is not supported yet"

APP_DETECTION_MODEL = "openai/gpt-5.4-nano"
