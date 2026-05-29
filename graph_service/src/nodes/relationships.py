from __future__ import annotations

from neomodel import AsyncStructuredRel, JSONProperty, StringProperty

_PERMISSION_EFFECTS: dict[str, str] = {
    "grant": "Grant",
    "mute": "Mute",
}


class HasPermissionRel(AsyncStructuredRel):
    """Carries the permission type on a HAS_PERMISSION edge.

    ``permission`` is a free-form string so integrations can define their own
    values ("read_only", "read_write", "admin", "download", …) without
    requiring a schema change.

    ``effect`` states whether the edge grants or removes the permission.
    When unset, integrations should treat the edge as a grant.

    ``extra`` is an optional schemaless JSON blob for integration-specific
    metadata (e.g. Salesforce object vs field access). Integrations validate
    their own ``extra`` shapes outside this node model.
    """

    permission = StringProperty(required=True)
    effect = StringProperty(choices=_PERMISSION_EFFECTS)
    extra = JSONProperty()
