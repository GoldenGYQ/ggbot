'''
会话元数据类，用于存储会话的元数据。
'''
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _now_ms() -> int:
    return int(time.time() * 1000)


def _sanitize_title(title: str) -> str:
    t = (title or "").strip()
    if not t:
        return "Untitled"
    # Single-line, no excessive whitespace.
    t = " ".join(t.split())
    # Avoid giant titles.
    if len(t) > 80:
        t = t[:77] + "..."
    return t


@dataclass
class SessionMeta:
    session_id: str
    title: str = "Untitled"
    user_turns: int = 0
    title_gen_turn: int = 0  # last user_turn at which title was generated
    created_ms: int = 0
    updated_ms: int = 0

    @classmethod
    def from_dict(cls, session_id: str, data: dict[str, Any]) -> "SessionMeta":
        """从字典创建会话元数据。"""
        return cls(
            session_id=session_id,
            title=_sanitize_title(str(data.get("title") or "Untitled")),
            user_turns=int(data.get("user_turns") or 0),
            title_gen_turn=int(data.get("title_gen_turn") or 0),
            created_ms=int(data.get("created_ms") or 0),
            updated_ms=int(data.get("updated_ms") or 0),
        )

    '''
    将会话元数据转换为字典。
    '''
    def to_dict(self) -> dict[str, Any]:
        return {
            "title": _sanitize_title(self.title),
            "user_turns": int(self.user_turns),
            "title_gen_turn": int(self.title_gen_turn),
            "created_ms": int(self.created_ms),
            "updated_ms": int(self.updated_ms),
        }


'''
获取会话元数据文件的路径。
'''
def meta_path(transcript_dir: Path) -> Path:
    return (transcript_dir / "sessions.json").resolve()


'''
加载所有会话的元数据。
如果文件不存在或格式错误，返回空字典。
'''
def load_all(transcript_dir: Path) -> dict[str, SessionMeta]:
    path = meta_path(transcript_dir)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}

    out: dict[str, SessionMeta] = {}
    for session_id, data in raw.items():
        if not isinstance(session_id, str) or not isinstance(data, dict):
            continue
        out[session_id] = SessionMeta.from_dict(session_id, data)
    return out


'''
保存会话元数据到文件。
'''
def save_all(transcript_dir: Path, metas: dict[str, SessionMeta]) -> None:
    path = meta_path(transcript_dir)
    data = {sid: meta.to_dict() for sid, meta in metas.items()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


'''
获取会话元数据，如果不存在则创建一个新的。
'''
def get_or_create(metas: dict[str, SessionMeta], session_id: str) -> SessionMeta:
    meta = metas.get(session_id)
    if meta is not None:
        return meta
    now = _now_ms()
    meta = SessionMeta(session_id=session_id, created_ms=now, updated_ms=now)
    metas[session_id] = meta
    return meta


'''
递增会话的用户回合数。
'''
def increment_user_turn(metas: dict[str, SessionMeta], session_id: str) -> int:
    meta = get_or_create(metas, session_id)
    meta.user_turns += 1
    meta.updated_ms = _now_ms()
    return meta.user_turns


'''
设置会话的标题。
'''
def set_title(metas: dict[str, SessionMeta], session_id: str, *, title: str, title_gen_turn: int) -> None:
    """设置会话的标题。"""
    meta = get_or_create(metas, session_id)
    meta.title = _sanitize_title(title)
    meta.title_gen_turn = int(title_gen_turn)
    meta.updated_ms = _now_ms()
