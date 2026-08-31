from __future__ import annotations

from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO_ROOT = next(
    (parent for parent in _HERE.parents if (parent / ".env").is_file() or (parent / "uv.lock").is_file()),
    Path("/app"),
)
ENV_FILE = str(_REPO_ROOT / ".env") if (_REPO_ROOT / ".env").is_file() else None
