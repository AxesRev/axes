"""Supported application identifiers for access-request routing."""

from __future__ import annotations

from typing import Literal

SupportedApp = Literal["github", "salesforce"]

SUPPORTED_APPS: frozenset[str] = frozenset({"github", "salesforce"})

# Permission values exactly as ingestion stores them on HAS_PERMISSION.permission,
# with a short description for the Jev permission-type tournament.
PERMISSION_TYPES_BY_APP: dict[str, dict[str, str]] = {
    "salesforce": {
        "read": "view records of the object",
        "create": "create new records of the object",
        "edit": "update records of the object",
        "delete": "delete records of the object",
        "view_all": "view every record of the object regardless of sharing",
        "modify_all": "edit and delete every record of the object regardless of sharing",
        "all": "full access to a specific record, like its owner (read, edit, delete, share)",
    },
    "github": {
        "READ": "read and clone the repository",
        "TRIAGE": "manage issues and pull requests without write access",
        "WRITE": "push to the repository",
        "MAINTAIN": "manage the repository without admin or destructive actions",
        "ADMIN": "full admin access to the repository",
    },
}

UNSUPPORTED_APP_MESSAGE = "sorry this application is not supported yet"

APP_DETECTION_MODEL = "openai/gpt-4o-mini"
