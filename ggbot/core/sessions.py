from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DefaultSessions:
    chat: str
    repl: str


def _short_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]


def default_sessions(*, workspace_root: Path, transcript_dir: Path) -> DefaultSessions:
    """Return stable default session IDs for this workspace.

    If transcript_dir is inside workspace_root (the default), we use simple names
    ("chat", "repl"). If transcript_dir is shared across workspaces, we suffix
    a short hash of workspace_root to avoid collisions.
    """

    ws = workspace_root.resolve()
    td = transcript_dir.resolve()

    try:
        in_workspace = td.is_relative_to(ws)
    except AttributeError:
        # Python < 3.9 fallback (unlikely here, but harmless).
        in_workspace = str(td).startswith(str(ws))

    if in_workspace:
        return DefaultSessions(chat="chat", repl="repl")

    suffix = _short_hash(str(ws))
    return DefaultSessions(chat=f"chat_{suffix}", repl=f"repl_{suffix}")
