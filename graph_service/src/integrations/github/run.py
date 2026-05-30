"""Run GitHub App installation ingestion (no graph wipe)."""

from __future__ import annotations

import logging

from integrations.github.ingestion.installation import fetch_installation

logger = logging.getLogger(__name__)


async def run_github_ingestion(installation_ids: list[int]) -> None:
    """Fetch and ingest all given GitHub App installations into the graph."""
    if not installation_ids:
        logger.warning("github_ingestion_skipped_no_installation_ids")
        return

    for installation_id in installation_ids:
        logger.info("github_fetch_start installation_id=%s", installation_id)
        await fetch_installation(installation_id)
        logger.info("github_fetch_complete installation_id=%s", installation_id)
