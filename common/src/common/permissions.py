"""HAS_PERMISSION.permission values shared by graph ingestion and the agent.

Ingestion writes only these strings to ``HAS_PERMISSION.permission``. The agent offers
``PERMISSION_TYPES_BY_APP`` to Jev and matches grant paths on the same values, so a
value added to ingestion must be added here too.
"""

from __future__ import annotations

# Salesforce object permissions (Profile / PermissionSet → Scope).
PERMISSION_READ = "read"
PERMISSION_CREATE = "create"
PERMISSION_EDIT = "edit"
PERMISSION_DELETE = "delete"
PERMISSION_VIEW_ALL = "view_all"
PERMISSION_MODIFY_ALL = "modify_all"
# Salesforce record shares (__Share AccessLevel Read / Edit / All → Resource).
PERMISSION_ALL = "all"
# Salesforce system permissions (Profile / PermissionSet → Scope of kind system_permission).
PERMISSION_ENABLED = "enabled"
# Record ownership. Not ingested yet, so not offered in PERMISSION_TYPES_BY_APP.
PERMISSION_OWNER = "owner"

# GitHub RepositoryPermission enum values, stored as GitHub returns them.
GITHUB_PERMISSION_READ = "READ"
GITHUB_PERMISSION_TRIAGE = "TRIAGE"
GITHUB_PERMISSION_WRITE = "WRITE"
GITHUB_PERMISSION_MAINTAIN = "MAINTAIN"
GITHUB_PERMISSION_ADMIN = "ADMIN"

PERMISSION_EFFECT_GRANT = "grant"
PERMISSION_EFFECT_MUTE = "mute"

# Permission value → short description for the Jev permission-type tournament.
PERMISSION_TYPES_BY_APP: dict[str, dict[str, str]] = {
    "salesforce": {
        PERMISSION_READ: "view records of the object",
        PERMISSION_CREATE: "create new records of the object",
        PERMISSION_EDIT: "update records of the object",
        PERMISSION_DELETE: "delete records of the object",
        PERMISSION_VIEW_ALL: "view every record of the object regardless of sharing",
        PERMISSION_MODIFY_ALL: "edit and delete every record of the object regardless of sharing",
        PERMISSION_ALL: "full access to a specific record, like its owner (read, edit, delete, share)",
        PERMISSION_ENABLED: "have an org-wide system permission such as API Enabled or Export Reports",
    },
    "github": {
        GITHUB_PERMISSION_READ: "read and clone the repository",
        GITHUB_PERMISSION_TRIAGE: "manage issues and pull requests without write access",
        GITHUB_PERMISSION_WRITE: "push to the repository",
        GITHUB_PERMISSION_MAINTAIN: "manage the repository without admin or destructive actions",
        GITHUB_PERMISSION_ADMIN: "full admin access to the repository",
    },
}
