from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DefaultSessions:
    chat: str
    repl: str
    tui: str


def _short_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]


def default_sessions(*, workspace_root: Path, transcript_dir: Path) -> DefaultSessions:
    """返回该工作区稳定的默认会话 ID。

            如果 transcript_dir 位于 workspace_root 内部（默认情况），我们使用简单名称
    （"chat"、"repl"）。如果 transcript_dir 在多个工作区之间共享，我们会附加
    workspace_root 的短哈希值以避免冲突。
    """

    ws = workspace_root.resolve()
    td = transcript_dir.resolve()

    try:
        in_workspace = td.is_relative_to(ws)
    except AttributeError:
        # Python < 3.9 fallback (unlikely here, but harmless).
        in_workspace = str(td).startswith(str(ws))

    if in_workspace:
        return DefaultSessions(chat="chat", repl="repl", tui="tui")

    suffix = _short_hash(str(ws))
    return DefaultSessions(chat=f"chat_{suffix}", repl=f"repl_{suffix}", tui=f"tui_{suffix}")
