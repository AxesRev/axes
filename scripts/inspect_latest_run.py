#!/usr/bin/env python3
"""Fetch the latest ``runs`` row and a compact checkpoint transcript.

Includes: who sent each turn (human / assistant), assistant text output, and
semantic doc corpus chunks (``doc_corpus_context``) when present in checkpoint state.
In the ``access_grant_execution`` subgraph, tool calls are shown with ``url``,
``payload``, and ``response`` only. Other subgraphs omit tool traffic.

Writes UTF-8 text under ``.scratch/`` (gitignored) by default. Includes per-field
LLM ``justification`` strings (``domain_result`` / ``resource_result`` /
``permission_result``) and validator feedback when present in checkpoint state.

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
_TEXT_SOFT_LIMIT: int = 4000
_GRANT_EXECUTION_NS_PREFIX: str = "access_grant_execution"

_JUSTIFICATION_KEYS_ORDER: tuple[str, ...] = (
    "domain_result",
    "resource_result",
    "permission_result",
    "domain_feedback",
    "resource_feedback",
    "permission_feedback",
)


def _trunc_text(text: str, limit: int = _TEXT_SOFT_LIMIT) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… [{len(text) - limit} more chars]"


def _channel_values_dict(checkpoint: Any) -> dict[str, Any]:
    if not isinstance(checkpoint, dict):
        return {}
    raw = checkpoint.get("channel_values")
    return raw if isinstance(raw, dict) else {}


def _normalize_field_result_snap(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return {"value": None, "justification": f"(non-dict state: {raw!r})"}
    if "justification" not in raw and "value" not in raw:
        return None
    return {"value": raw.get("value"), "justification": raw.get("justification")}


def _justification_slice(channel_values: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("domain_result", "resource_result", "permission_result"):
        if key not in channel_values:
            continue
        norm = _normalize_field_result_snap(channel_values[key])
        if norm is not None:
            out[key] = norm
    for key in ("domain_feedback", "resource_feedback", "permission_feedback"):
        if key not in channel_values:
            continue
        v = channel_values[key]
        if v is not None and str(v).strip():
            out[key] = str(v).strip()
    return out


def _snap_json(snap: dict[str, Any]) -> str:
    return json.dumps(snap, sort_keys=True, ensure_ascii=False, default=str)


def _format_justification_slice(snap: dict[str, Any]) -> list[str]:
    lines: list[str] = ["  --- Structured justifications (FieldResult + validator feedback) ---"]
    for key in _JUSTIFICATION_KEYS_ORDER:
        if key not in snap:
            continue
        val = snap[key]
        if isinstance(val, dict) and "justification" in val:
            lines.append(f"  {key}:")
            lines.append(f"    value: {val.get('value')!r}")
            lines.append("    justification:")
            body = _trunc_text(str(val.get("justification", "")), limit=8000)
            for ln in body.splitlines():
                lines.append(f"      {ln}")
        else:
            lines.append(f"  {key}:")
            body = _trunc_text(str(val), limit=8000)
            for ln in body.splitlines():
                lines.append(f"    {ln}")
    lines.append("")
    return lines


def _doc_corpus_context_text(channel_values: dict[str, Any]) -> str:
    raw = channel_values.get("doc_corpus_context")
    if raw is None:
        return ""
    return str(raw).strip()


def _format_doc_corpus_context_block(text: str, *, limit: int = 12000) -> list[str]:
    if not text:
        return []
    lines: list[str] = ["  --- Semantic doc corpus chunks ---"]
    body = _trunc_text(text, limit=limit)
    for ln in body.splitlines():
        lines.append(f"  {ln}")
    lines.append("")
    return lines


def _format_final_doc_corpus_context(checkpoints: list[Any]) -> str:
    if not checkpoints:
        return ""
    last_cv = _channel_values_dict(checkpoints[-1].checkpoint)
    text = _doc_corpus_context_text(last_cv)
    if not text:
        return ""
    lines: list[str] = [
        "=" * 72,
        "SEMANTIC DOC CORPUS CHUNKS (last checkpoint; injected into prompts)",
        "=" * 72,
        "",
    ]
    lines.extend(_format_doc_corpus_context_block(text, limit=20000))
    return "\n".join(lines)


def _format_final_field_justifications(checkpoints: list[Any]) -> str:
    if not checkpoints:
        return ""
    last_cv = _channel_values_dict(checkpoints[-1].checkpoint)
    snap = _justification_slice(last_cv)
    field_keys = ("domain_result", "resource_result", "permission_result")
    if not any(k in snap for k in field_keys):
        return ""
    lines: list[str] = [
        "=" * 72,
        "FINAL FIELD JUSTIFICATIONS (last checkpoint; domain / resource / permission)",
        "=" * 72,
        "",
    ]
    for key in field_keys:
        if key not in snap:
            continue
        val = snap[key]
        if not isinstance(val, dict):
            continue
        lines.append(f"{key}:")
        lines.append(f"  value: {val.get('value')!r}")
        lines.append("  justification:")
        body = _trunc_text(str(val.get("justification", "")), limit=12000)
        for ln in body.splitlines():
            lines.append(f"    {ln}")
        lines.append("")
    lines.append("")
    return "\n".join(lines)


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            else:
                parts.append(json.dumps(block, ensure_ascii=False, default=str))
        return "\n".join(parts)
    return json.dumps(content, ensure_ascii=False, default=str)


def _serialize_messages(msgs: Any) -> list[dict[str, Any]]:
    if msgs is None:
        return []
    if isinstance(msgs, BaseMessage):
        msgs = [msgs]
    if isinstance(msgs, list) and msgs and isinstance(msgs[0], BaseMessage):
        return messages_to_dict(msgs)
    if isinstance(msgs, list):
        return [m for m in msgs if isinstance(m, dict)]
    return []


def _coerce_data(msg: dict[str, Any]) -> dict[str, Any]:
    data = msg.get("data")
    if isinstance(data, dict):
        return data
    return msg


def _is_grant_execution_ns(ns: str) -> bool:
    return ns.startswith(_GRANT_EXECUTION_NS_PREFIX)


def _parse_tool_call_args(tool_name: str, args: Any) -> tuple[str | None, Any | None]:
    if not isinstance(args, dict):
        return None, args

    url_raw = args.get("url")
    if url_raw is not None:
        payload = args.get("data")
        if payload is None:
            payload = args.get("params")
        return str(url_raw), payload

    text = args.get("text")
    if isinstance(text, str) and text.strip():
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            parsed_url = parsed.get("url")
            url = str(parsed_url) if parsed_url is not None else None
            return url, parsed.get("data")

    if tool_name == "json_explorer":
        payload = args.get("__arg1")
        if payload is None:
            payload = args.get("query")
        return None, payload

    return None, args or None


def _format_json_field(value: Any) -> str:
    if value is None:
        return "(none)"
    if isinstance(value, str):
        return _trunc_text(value)
    return _trunc_text(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _tool_response_text(data: dict[str, Any]) -> str:
    content = _content_to_text(data.get("content"))
    if content.strip():
        return _trunc_text(content)
    status = data.get("status")
    if status:
        return f"(empty body; status={status})"
    return "(empty)"


def _format_grant_tool_call_block(*, url: str | None, payload: Any, response: str) -> list[str]:
    lines: list[str] = ["--- Tool call ---"]
    lines.append(f"url: {url if url else '(none)'}")
    lines.append("payload:")
    for ln in _format_json_field(payload).splitlines():
        lines.append(f"  {ln}")
    lines.append("response:")
    for ln in response.splitlines():
        lines.append(f"  {ln}")
    lines.append("")
    return lines


def _format_grant_execution_new_messages(
    new_msgs: list[dict[str, Any]],
    pending: dict[str, tuple[str | None, Any]],
) -> tuple[list[list[str]], dict[str, tuple[str | None, Any]]]:
    blocks: list[list[str]] = []
    for msg in new_msgs:
        mtype = str(msg.get("type", "?")).lower()
        data = _coerce_data(msg)

        if mtype == "ai":
            for tc in data.get("tool_calls") or []:
                if not isinstance(tc, dict):
                    continue
                tc_id = tc.get("id")
                if not tc_id:
                    continue
                name = str(tc.get("name", ""))
                url, payload = _parse_tool_call_args(name, tc.get("args") or {})
                pending[str(tc_id)] = (url, payload)
            if not data.get("tool_calls"):
                block_lines = _format_compact_message_lines(msg)
                if block_lines:
                    blocks.append(block_lines)
            continue

        if mtype == "tool":
            tc_id = str(data.get("tool_call_id") or "")
            url, payload = pending.pop(tc_id, (None, None))
            response = _tool_response_text(data)
            blocks.append(
                _format_grant_tool_call_block(url=url, payload=payload, response=response),
            )
            continue

        block_lines = _format_compact_message_lines(msg)
        if block_lines:
            blocks.append(block_lines)

    return blocks, pending


def _collect_grant_execution_tool_calls(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pending: dict[str, tuple[str | None, Any]] = {}
    collected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for msg in messages:
        mtype = str(msg.get("type", "?")).lower()
        data = _coerce_data(msg)

        if mtype == "ai":
            for tc in data.get("tool_calls") or []:
                if not isinstance(tc, dict):
                    continue
                tc_id = tc.get("id")
                if not tc_id:
                    continue
                name = str(tc.get("name", ""))
                url, payload = _parse_tool_call_args(name, tc.get("args") or {})
                pending[str(tc_id)] = (url, payload)
            continue

        if mtype != "tool":
            continue

        tc_id = str(data.get("tool_call_id") or "")
        if not tc_id or tc_id in seen_ids:
            continue
        seen_ids.add(tc_id)
        url, payload = pending.get(tc_id, (None, None))
        collected.append(
            {
                "tool_call_id": tc_id,
                "url": url,
                "payload": payload,
                "response": _tool_response_text(data),
            },
        )

    return collected


def _format_final_grant_execution_tool_calls(checkpoints: list[Any]) -> str:
    best_messages: list[dict[str, Any]] = []
    for tup in checkpoints:
        ns = (tup.config.get("configurable") or {}).get("checkpoint_ns") or ""
        if not _is_grant_execution_ns(ns):
            continue
        channel_values = _channel_values_dict(tup.checkpoint)
        serialized = _serialize_messages(channel_values.get("messages"))
        if len(serialized) > len(best_messages):
            best_messages = serialized

    tool_calls = _collect_grant_execution_tool_calls(best_messages)
    if not tool_calls:
        return ""

    lines: list[str] = [
        "=" * 72,
        "GRANT EXECUTION TOOL CALLS (access_grant_execution subgraph)",
        "=" * 72,
        "",
    ]
    for idx, call in enumerate(tool_calls, start=1):
        lines.append(f"[tool call {idx}]")
        lines.extend(
            _format_grant_tool_call_block(
                url=call["url"],
                payload=call["payload"],
                response=call["response"],
            ),
        )
    return "\n".join(lines)


def _format_compact_message_lines(msg: dict[str, Any]) -> list[str]:
    mtype = str(msg.get("type", "?")).lower()
    data = _coerce_data(msg)
    lines: list[str] = []

    if mtype == "human":
        text = _trunc_text(_content_to_text(data.get("content")))
        lines.append("From: human")
        if text:
            lines.append("Message:")
            lines.extend(text.splitlines())
        lines.append("")
        return lines

    if mtype == "ai":
        text = _trunc_text(_content_to_text(data.get("content")))
        if not text.strip():
            return []
        lines.append("From: assistant")
        lines.append("Output:")
        lines.extend(text.splitlines())
        lines.append("")
        return lines

    if mtype == "tool":
        return []

    lines.append(f"From: {mtype} (summary only)")
    snippet = json.dumps(data, ensure_ascii=False, default=str)
    lines.append(_trunc_text(snippet, limit=1500))
    lines.append("")
    return lines


def _extract_last_human_from_input(inp: Any) -> str:
    if not isinstance(inp, dict):
        return _trunc_text(json.dumps(inp, ensure_ascii=False, default=str), limit=800)
    msgs = inp.get("messages")
    if isinstance(msgs, list):
        for m in reversed(msgs):
            if not isinstance(m, dict):
                continue
            if str(m.get("type", "")).lower() == "human":
                return _trunc_text(_content_to_text(_coerce_data(m).get("content")), limit=2000)
            role = m.get("role")
            if role == "user":
                return _trunc_text(_content_to_text(m.get("content")), limit=2000)
    return _trunc_text(json.dumps(inp, ensure_ascii=False, default=str), limit=800)


def _extract_final_output_summary(out: Any) -> str:
    if not isinstance(out, dict):
        return _trunc_text(json.dumps(out, ensure_ascii=False, default=str), limit=800)
    msgs = out.get("messages")
    if isinstance(msgs, list):
        for m in reversed(msgs):
            if not isinstance(m, dict):
                continue
            if str(m.get("type", "")).lower() == "ai":
                return _trunc_text(_content_to_text(_coerce_data(m).get("content")), limit=4000)
            if m.get("role") == "assistant":
                return _trunc_text(_content_to_text(m.get("content")), limit=4000)
    return _trunc_text(json.dumps(out, ensure_ascii=False, default=str), limit=1200)


def _format_run_section(row: Sequence[Any]) -> str:
    run_id, thread_id, status, error_message, inp, out, created_at = row
    lines: list[str] = [
        "=" * 72,
        "LATEST RUN",
        "=" * 72,
        f"run_id:         {run_id}",
        f"thread_id:      {thread_id}",
        f"status:         {status}",
        f"created_at:     {created_at}",
        f"error_message:  {error_message if error_message else '(none)'}",
        "",
        "--- Caller prompt (last human message in run input, if any) ---",
        _extract_last_human_from_input(inp),
        "",
        "--- Final run output (last assistant text in run output, if any) ---",
        _extract_final_output_summary(out),
        "",
    ]
    return "\n".join(lines)


async def _collect_checkpoints(*, thread_id: str, run_id: str | None, limit: int) -> list[Any]:
    conn_url = settings.db.database_url_sync
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    batch: list[Any] = []
    async with AsyncPostgresSaver.from_conn_string(conn_url) as saver:
        async for tup in saver.alist(config, limit=limit):
            meta = dict(tup.metadata or {})
            if run_id is not None and meta.get("run_id") != run_id:
                continue
            batch.append(tup)
    batch.reverse()
    return batch


def _render_checkpoint_transcript(checkpoints: list[Any]) -> str:
    """Turn ordered checkpoints into compact text (delta messages + justification state)."""
    lines: list[str] = [
        "=" * 72,
        "CHECKPOINT TRANSCRIPT (oldest → newest; only new messages per snapshot)",
        "=" * 72,
        "",
    ]

    prev_len_by_ns: dict[str, int] = {}
    prev_just_snap: dict[str, Any] = {}
    prev_doc_corpus = ""
    grant_pending_tool_calls: dict[str, tuple[str | None, Any]] = {}
    shown = 0
    for tup in checkpoints:
        ns = (tup.config.get("configurable") or {}).get("checkpoint_ns") or ""
        checkpoint = tup.checkpoint if isinstance(tup.checkpoint, dict) else {}
        channel_values = _channel_values_dict(checkpoint)
        messages = channel_values.get("messages")
        serialized = _serialize_messages(messages)
        prev_len = prev_len_by_ns.get(ns, 0)
        new_msgs = serialized[prev_len:]
        prev_len_by_ns[ns] = len(serialized)

        just_snap = _justification_slice(channel_values)
        just_changed = _snap_json(just_snap) != _snap_json(prev_just_snap)
        doc_corpus = _doc_corpus_context_text(channel_values)
        doc_corpus_changed = doc_corpus != prev_doc_corpus

        rendered_blocks: list[list[str]] = []
        if _is_grant_execution_ns(ns):
            rendered_blocks, grant_pending_tool_calls = _format_grant_execution_new_messages(
                new_msgs,
                grant_pending_tool_calls,
            )
        else:
            for msg in new_msgs:
                block_lines = _format_compact_message_lines(msg)
                if block_lines:
                    rendered_blocks.append(block_lines)

        if not rendered_blocks and not just_changed and not doc_corpus_changed:
            continue

        shown += 1
        lines.append(f"[checkpoint {shown}] ns={ns!r}")

        if doc_corpus_changed and doc_corpus:
            lines.extend(_format_doc_corpus_context_block(doc_corpus))
            prev_doc_corpus = doc_corpus

        if just_changed:
            if just_snap:
                lines.extend(_format_justification_slice(just_snap))
            prev_just_snap = dict(just_snap)

        for block_lines in rendered_blocks:
            for ln in block_lines:
                if ln == "":
                    lines.append("")
                else:
                    lines.append(f"  {ln}")
            lines.append("")

    lines.append("=" * 72)
    lines.append(f"Snapshots printed: {shown} (of {len(checkpoints)} checkpoints scanned)")
    lines.append("")
    doc_corpus_block = _format_final_doc_corpus_context(checkpoints)
    if doc_corpus_block:
        lines.append(doc_corpus_block)
    final_block = _format_final_field_justifications(checkpoints)
    if final_block:
        lines.append(final_block)
    grant_tool_block = _format_final_grant_execution_tool_calls(checkpoints)
    if grant_tool_block:
        lines.append(grant_tool_block)
    return "\n".join(lines)


async def _format_checkpoints(*, thread_id: str, run_id: str | None, limit: int) -> str:
    checkpoints = await _collect_checkpoints(thread_id=thread_id, run_id=run_id, limit=limit)
    return _render_checkpoint_transcript(checkpoints)


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
        help="Max checkpoints to scan from storage (newest first before reorder)",
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
            f"Generated at (UTC): {generated_at}",
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
