from __future__ import annotations

from neomodel import AsyncStructuredRel, JSONProperty, StringProperty


class HasPermissionRel(AsyncStructuredRel):
    """Carries the permission type on a HAS_PERMISSION edge.

    ``permission`` is a free-form string so integrations can define their own
    values ("read_only", "read_write", "admin", "download", …) without
    requiring a schema change.

    ``extra`` is an optional schemaless JSON blob for integration-specific
    metadata (e.g. Salesforce object vs field access). Integrations validate
    their own ``extra`` shapes outside this node model.
    """

    permission = StringProperty(required=True)
    extra = JSONProperty()
