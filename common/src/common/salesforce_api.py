"""Salesforce REST API version used by every client.

simple_salesforce falls back to its own built-in default (59.0), which hides newer fields such as
recent PermissionSet system permissions. Bump this when Salesforce ships a release we need.
"""

from __future__ import annotations

SALESFORCE_API_VERSION = "68.0"
