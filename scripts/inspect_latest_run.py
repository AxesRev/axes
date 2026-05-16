#!/usr/bin/env python3
"""Fetch the latest row from ``runs`` and append LangGraph checkpoint detail (human-readable).

Writes UTF-8 text to a path under ``.scratch/`` (gitignored) by default.

Run from repo root::

    uv run --package aegra-api python scripts/inspect_latest_run.py

Requires the same ``.env`` / DB settings as Aegra (see ``aegra_api.settings``).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from langchain_core.messages import BaseMessage, messages_to_dict
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "libs" / "aegra-api" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from aegra_api.settings import settings  # noqa: E402

DEFAULT_OUTPUT_RELATIVE = Path(".scratch") / "latest-run-inspect.txt"
_DEFAULT_CHECKPOINT_LIMIT: int = 60


def _short_json(obj: Any, limit: int = 8000) -> str:
    raw = json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    if len(raw) <= limit:
        return raw
    return raw[:limit] + f"\n... [{len(raw) - limit} chars truncated]\n"


def _serialize_messages(msgs: Any) -> list[dict[str, Any]]:
    if msgs is None:
        return []
    if isinstance(msgs, BaseMessage):
        msgs = [msgs]
    if isinstance(msgs, list) and msgs and isinstance(msgs[0], BaseMessage):
        return messages_to_dict(msgs)
    return msgs if isinstance(msgs, list) else [msgs]


def _format_run_section(row: Sequence[Any]) -> str:
    """Build human-readable summary for one ``runs`` row."""
    run_id, thread_id, status, error_message, inp, out, created_at = row
    lines: list[str] = [
        "=" * 88,
        "LATEST RUN (ORDER BY created_at DESC, LIMIT 1)",
        "=" * 88,
        f"run_id:      {run_id}",
        f"thread_id:   {thread_id}",
        f"status:      {status}",
        f"created_at:  {created_at}",
        f"error_message: {error_message if error_message else '(none)'}",
        "",
        "--- input ---",
        _short_json(inp if inp is not None else {}, limit=12000),
        "",
        "--- output ---",
        _short_json(out if out is not None else {}, limit=12000),
        "",
    ]
    return "\n".join(lines)


async def _format_checkpoints(*, thread_id: str, run_id: str | None, limit: int) -> str:
    conn_url = settings.db.database_url_sync
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    lines: list[str] = [
        "=" * 88,
        f"CHECKPOINTS (thread_id={thread_id!r}, run_id filter={run_id!r})",
        "=" * 88,
        "",
    ]

    async with AsyncPostgresSaver.from_conn_string(conn_url) as saver:
        n = 0
        async for tup in saver.alist(config, limit=limit):
            meta = dict(tup.metadata or {})
            if run_id is not None and meta.get("run_id") != run_id:
                continue

            ns = (tup.config.get("configurable") or {}).get("checkpoint_ns") or ""
            cp_id = tup.checkpoint.get("id", "?")
            step = meta.get("step")
            source = meta.get("source")

            channel_values = tup.checkpoint.get("channel_values") or {}
            messages = channel_values.get("messages")

            lines.append("\n" + "=" * 88)
            lines.append(f"checkpoint_ns={ns!r}")
            lines.append(f"checkpoint_id={cp_id}")
            lines.append(f"metadata: step={step} source={source} run_id={meta.get('run_id')}")

            if messages is not None:
                serialized = _serialize_messages(messages)
                lines.append("\n--- messages (LLM / tool I/O) ---")
                lines.append(_short_json(serialized))

            other_keys = sorted(k for k in channel_values if k != "messages")
            if other_keys:
                preview: dict[str, Any] = {}
                for k in other_keys:
                    v = channel_values[k]
                    if isinstance(v, BaseMessage):
                        preview[k] = messages_to_dict([v])
                    elif isinstance(v, list) and v and isinstance(v[0], BaseMessage):
                        preview[k] = messages_to_dict(v)
                    else:
                        preview[k] = v
                lines.append("\n--- other channel_values (compact) ---")
                lines.append(_short_json(preview, limit=6000))

            pending = tup.pending_writes or []
            if pending:
                lines.append("\n--- pending_writes (tool/results not yet merged) ---")
                for task_id, channel, value in pending:
                    lines.append(f"  channel={channel} task_id={task_id}")
                    if channel == "messages" and isinstance(value, list):
                        lines.append(_short_json(_serialize_messages(value), limit=4000))
                    elif channel == "branch:to:tools":
                        lines.append("  (routing)")
                    else:
                        lines.append(_short_json(value, limit=4000))

            n += 1

        lines.append("\n" + "=" * 88)
        lines.append(f"Total checkpoints printed (after run_id filter): {n}")
        lines.append("")

    return "\n".join(lines)


def _fetch_latest_run_row() -> Sequence[Any] | None:
    sql = """
        SELECT run_id, thread_id, status, error_message, input, output, created_at
        FROM runs
        ORDER BY created_at DESC
        LIMIT 1
    """
    with psycopg.connect(settings.db.database_url_sync) as conn, conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchone()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=_REPO_ROOT / DEFAULT_OUTPUT_RELATIVE,
        help=f"Output file path (default: {_REPO_ROOT / DEFAULT_OUTPUT_RELATIVE})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=_DEFAULT_CHECKPOINT_LIMIT,
        help="Max checkpoints to scan (newest first)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Also print the report to stdout",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    row = _fetch_latest_run_row()
    if row is None:
        msg = "No rows in table `runs`.\n"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(msg, encoding="utf-8")
        print(msg, file=sys.stderr)
        sys.exit(1)

    run_id_s = str(row[0])
    thread_id_s = str(row[1])

    header = _format_run_section(row)
    footer = asyncio.run(
        _format_checkpoints(thread_id=thread_id_s, run_id=run_id_s, limit=args.limit),
    )

    generated_at = datetime.now(tz=UTC).isoformat()
    report = "\n".join(
        [
            f"Generated at (local): {generated_at}",
            "",
            header,
            footer,
        ]
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")

    if args.stdout:
        print(report)

    print(f"Wrote {args.output.resolve()} ({len(report)} chars)", file=sys.stderr)


if __name__ == "__main__":
    main()
