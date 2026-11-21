"""ArcadeDB access for graph ingestion: one database per tenant.

``setup_graph`` opens the Bolt driver and HTTP admin client. ``tenant_graph`` selects a
tenant's database for every ``graph_query`` inside it, creating (or resetting) the
database, its schema and its read-only agent user first.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any

import httpx
from common.graph_schema import schema_sql
from common.graph_tenancy import tenant_database, tenant_reader_password, tenant_reader_user

from integrations.github.settings import get_runner_settings
from neo4j import AsyncDriver, AsyncGraphDatabase

logger = logging.getLogger(__name__)

_ROOT_USER = "root"
_READER_GROUP = "readonly"

_driver: AsyncDriver | None = None
_http: httpx.AsyncClient | None = None
_current_database: ContextVar[str | None] = ContextVar("graph_database", default=None)
_reset_databases: set[str] = set()


async def setup_graph() -> None:
    """Open the Bolt driver and the HTTP admin client."""
    global _driver, _http
    runner = get_runner_settings()
    _driver = AsyncGraphDatabase.driver(runner.ARCADEDB_BOLT_URI, auth=(_ROOT_USER, runner.ARCADEDB_ROOT_PASSWORD))
    _http = httpx.AsyncClient(
        base_url=runner.ARCADEDB_HTTP_URL.rstrip("/") + "/api/v1",
        auth=(_ROOT_USER, runner.ARCADEDB_ROOT_PASSWORD),
        timeout=120,
    )


async def teardown_graph() -> None:
    """Close the Bolt driver and HTTP client."""
    global _driver, _http
    if _driver is not None:
        await _driver.close()
        _driver = None
    if _http is not None:
        await _http.aclose()
        _http = None


def _admin() -> httpx.AsyncClient:
    if _http is None:
        raise RuntimeError("setup_graph() must run first")
    return _http


async def _server_command(command: str, *, ok_errors: tuple[int, ...] = ()) -> None:
    response = await _admin().post("/server", json={"command": command})
    if response.status_code in ok_errors:
        return
    if response.status_code >= 400:
        raise RuntimeError(f"ArcadeDB server command failed ({response.status_code}): {response.text[:500]}")


async def _database_exists(database: str) -> bool:
    response = await _admin().get(f"/exists/{database}")
    response.raise_for_status()
    return bool(response.json().get("result"))


async def _prepare_database(tenant_id: str, *, reset: bool) -> str:
    database = tenant_database(tenant_id)
    exists = await _database_exists(database)
    if reset and database not in _reset_databases and exists:
        await _server_command(f"drop database {database}")
        exists = False
        logger.info("graph_database_dropped database=%s", database)
    _reset_databases.add(database)
    if not exists:
        await _server_command(f"create database {database}", ok_errors=(409,))
        logger.info("graph_database_created database=%s", database)

    response = await _admin().post(f"/command/{database}", json={"language": "sqlscript", "command": schema_sql()})
    if response.status_code >= 400:
        raise RuntimeError(f"ArcadeDB schema setup failed ({response.status_code}): {response.text[:500]}")

    await _ensure_reader(tenant_id, database)
    return database


async def _ensure_reader(tenant_id: str, database: str) -> None:
    """(Re)create the tenant's read-only user so its password matches ARCADEDB_TENANT_KEY."""
    user = tenant_reader_user(tenant_id)
    password = tenant_reader_password(tenant_id, get_runner_settings().ARCADEDB_TENANT_KEY)
    await _server_command(f"drop user {user}", ok_errors=(400, 404, 500))
    payload = {"name": user, "password": password, "databases": {database: [_READER_GROUP]}}
    await _server_command(f"create user {json.dumps(payload)}")
    logger.info("graph_reader_ready database=%s user=%s", database, user)


@asynccontextmanager
async def tenant_graph(tenant_id: str, *, reset: bool = True) -> AsyncIterator[str]:
    """Run the enclosed ingestion against ``tenant_id``'s database.

    With ``reset`` the database is dropped and recreated the first time it is used in this
    process, which replaces the old wipe-everything step.
    """
    database = await _prepare_database(tenant_id, reset=reset)
    token = _current_database.set(database)
    try:
        yield database
    finally:
        _current_database.reset(token)


async def graph_query(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Run a Cypher statement on the current tenant database and return its rows."""
    database = _current_database.get()
    if database is None:
        raise RuntimeError("graph_query() must run inside tenant_graph()")
    if _driver is None:
        raise RuntimeError("setup_graph() must run first")
    async with _driver.session(database=database) as session:
        result = await session.run(query, params or {})
        return [record.data() async for record in result]
