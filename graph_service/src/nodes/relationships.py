from __future__ import annotations

from neomodel import AsyncStructuredRel, StringProperty


class HasPermissionRel(AsyncStructuredRel):
    """Carries the permission type on a HAS_PERMISSION edge.

    ``permission`` is a free-form string so integrations can define their own
    values ("read_only", "read_write", "admin", "download", …) without
    requiring a schema change.
    """

    permission = StringProperty(required=True)
