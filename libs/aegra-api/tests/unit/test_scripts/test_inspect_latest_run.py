"""Unit tests for inspect_latest_run grant-execution tool call formatting."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[5]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "inspect_latest_run.py"


def _load_inspect_module():
    spec = importlib.util.spec_from_file_location("inspect_latest_run", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["inspect_latest_run"] = module
    spec.loader.exec_module(module)
    return module


inspect_latest_run = _load_inspect_module()


def test_parse_tool_call_args_from_requests_put_text() -> None:
    args = {
        "text": ('{"url":"https://api.github.com/repos/org/repo/collaborators/user","data":{"permission":"push"}}'),
    }
    url, payload = inspect_latest_run._parse_tool_call_args("requests_put", args)
    assert url == "https://api.github.com/repos/org/repo/collaborators/user"
    assert payload == {"permission": "push"}


def test_parse_tool_call_args_from_requests_get_url() -> None:
    url, payload = inspect_latest_run._parse_tool_call_args(
        "requests_get",
        {"url": "https://api.github.com/repos/org/repo"},
    )
    assert url == "https://api.github.com/repos/org/repo"
    assert payload is None


def test_parse_tool_call_args_from_json_explorer() -> None:
    url, payload = inspect_latest_run._parse_tool_call_args(
        "json_explorer",
        {"__arg1": "Find collaborator endpoint"},
    )
    assert url is None
    assert payload == "Find collaborator endpoint"


def test_format_grant_execution_new_messages_pairs_tool_response() -> None:
    pending: dict[str, tuple[str | None, object]] = {}
    new_msgs = [
        {
            "type": "ai",
            "data": {
                "tool_calls": [
                    {
                        "name": "requests_put",
                        "args": {
                            "text": ('{"url":"https://api.github.com/repos/a/b","data":{"permission":"push"}}'),
                        },
                        "id": "call_1",
                    },
                ],
            },
        },
        {
            "type": "tool",
            "data": {
                "name": "requests_put",
                "tool_call_id": "call_1",
                "content": "",
                "status": "success",
            },
        },
    ]

    blocks, pending = inspect_latest_run._format_grant_execution_new_messages(new_msgs, pending)
    rendered = "\n".join(line for block in blocks for line in block)

    assert "url: https://api.github.com/repos/a/b" in rendered
    assert '"permission": "push"' in rendered
    assert "response:" in rendered
    assert "(empty body; status=success)" in rendered
    assert pending == {}
