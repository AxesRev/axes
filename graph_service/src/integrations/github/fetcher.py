"""CLI entry point for GitHub → graph ingestion.

Run directly:
    uv run --package aegra-graph-service python -m integrations.github.fetcher [INSTALLATION_ID]

When INSTALLATION_ID is omitted, every distinct non-null ``github_installation_id``
from ``user_identities`` is fetched (in sorted order). Pass one or more numeric IDs as
arguments to limit the run to those installations only.
"""

from __future__ import annotations

import asyncio
import logging
import sys

import asyncpg
from neomodel import adb

import nodes as _nodes_pkg  # noqa: F401 — registers all node classes with neomodel
from integrations.github.ingestion.installation import fetch_installation
from integrations.github.settings import RunnerSettings, get_runner_settings

logger = logging.getLogger(__name__)


async def _installation_ids_from_postgres(runner: RunnerSettings) -> list[int]:
    """Return sorted distinct installation IDs from ``user_identities``."""
    pg_conn = await asyncpg.connect(runner.postgres_url)
    try:
        rows = await pg_conn.fetch(
            "SELECT DISTINCT github_installation_id FROM user_identities "
            "WHERE github_installation_id IS NOT NULL "
            "ORDER BY github_installation_id"
        )
    finally:
        await pg_conn.close()

    ids: list[int] = []
    for row in rows:
        raw = row["github_installation_id"]
        try:
            ids.append(int(str(raw).strip()))
        except ValueError:
            logger.warning("skip_invalid_installation_id raw=%r", raw)

    return ids


async def _run_once() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    runner = get_runner_settings()

    if len(sys.argv) > 1:
        installation_ids = [int(arg) for arg in sys.argv[1:]]
        logger.info("installation_ids_from_cli=%s", installation_ids)
    else:
        installation_ids = await _installation_ids_from_postgres(runner)
        if not installation_ids:
            logger.error("no_installation_id_found_in_postgres")
            sys.exit(1)
        logger.info("resolved_installation_ids=%s", installation_ids)

    await adb.set_connection(runner.neomodel_url)
    await adb.install_all_labels()

    try:
        for installation_id in installation_ids:
            logger.info("fetch_start installation_id=%s", installation_id)
            await fetch_installation(installation_id)
    finally:
        await adb.close_connection()


if __name__ == "__main__":
    asyncio.run(_run_once())
