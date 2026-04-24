'''
会话存储类，用于存储和加载会话元数据。
'''

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .session_meta import SessionMeta, get_or_create, increment_user_turn, load_all, save_all, set_title
from .sessions import DefaultSessions


'''
会话存储类，用于存储和加载会话元数据。
'''

@dataclass
class SessionStore:
    transcript_dir: Path
    metas: dict[str, SessionMeta]

    @classmethod
    def load(cls, transcript_dir: Path) -> SessionStore:
        """从指定目录加载会话元数据。"""
        return cls(transcript_dir=transcript_dir, metas=load_all(transcript_dir))

    def save(self) -> None:
        """保存会话元数据到指定目录。"""
        save_all(self.transcript_dir, self.metas)

    def ensure(self, session_id: str) -> SessionMeta:
        """确保会话 ID 存在。如果不存在，则创建一个新的会话元数据。"""
        meta = get_or_create(self.metas, session_id)
        return meta

    def ensure_saved(self, session_id: str) -> SessionMeta:
        """确保会话元数据已保存到磁盘。
        如果会话元数据不存在，将创建一个新的会话元数据。
        """
        """确保会话 ID 存在并保存会话元数据。"""
        meta = self.ensure(session_id)
        self.save()
        return meta

    '''
    增加会话的用户回合数。
    如果会话不存在，会创建一个新会话。
    '''
    def increment_user_turn(self, session_id: str) -> int:
        """递增会话的用户轮次。"""
        turn_no = increment_user_turn(self.metas, session_id)
        self.save()
        """增加会话的用户回合数。"""    
        return turn_no

    def set_title(self, session_id: str, *, title: str, title_gen_turn: int) -> None:
        set_title(self.metas, session_id, title=title, title_gen_turn=title_gen_turn)
        self.save()

    def clear_session(self, session_id: str) -> None:
        """清除会话元数据。"""
        self.metas[session_id] = SessionMeta(session_id=session_id)
        """清除会话的所有消息。"""
        self.metas[session_id] = SessionMeta(session_id=session_id)
        self.save()

    def list_sessions(self, defaults: DefaultSessions) -> list[str]:
        """列出所有会话的会话 ID。"""
        existing = [path.stem for path in self.transcript_dir.glob("*.jsonl")]

        def mtime(session_id: str) -> float:
            path = self.transcript_dir / f"{session_id}.jsonl"
            try:
                return path.stat().st_mtime
            except Exception:
                return 0.0

        existing_sorted = sorted(existing, key=mtime, reverse=True)
        out: list[str] = []
        for session_id in (defaults.repl, defaults.chat, defaults.tui):
            if session_id not in out:
                out.append(session_id)
        for session_id in existing_sorted:
            if session_id not in out:
                out.append(session_id)
        return out

    '''
    获取会话的第一个用户消息。
    如果会话不存在或没有用户消息，返回 None。
    '''
    def first_user_message(self, session_id: str) -> str | None:
        """获取会话的第一个用户消息。"""    
        path = self.transcript_dir / f"{session_id}.jsonl"
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except Exception:
                        continue
                    if ev.get("type") != "model_message":
                        continue
                    data = ev.get("data") or {}
                    if not isinstance(data, dict):
                        continue
                    if data.get("role") == "user" and data.get("content"):
                        return str(data.get("content"))
        except Exception:
            return None
        return None

    '''
    获取会话的标题。
    如果会话不存在或没有标题，返回 "Untitled"。
    '''
    @staticmethod
    def title_for_list(self, session_id: str) -> str:
        """获取会话的标题。"""    
        meta = self.metas.get(session_id)
        if meta is not None and meta.title:
            return meta.title
        first = self.first_user_message(session_id)
        if first:
            first = " ".join(first.strip().split())
            return first[:60] + ("..." if len(first) > 60 else "")
        return "Untitled"