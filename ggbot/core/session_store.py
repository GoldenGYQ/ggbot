from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .session_meta import SessionMeta, get_or_create, increment_user_turn, load_all, save_all, set_title
from .sessions import DefaultSessions


@dataclass
class SessionStore:
    transcript_dir: Path
    metas: dict[str, SessionMeta]

    @classmethod
    def load(cls, transcript_dir: Path) -> SessionStore:
        return cls(transcript_dir=transcript_dir, metas=load_all(transcript_dir))

    def save(self) -> None:
        save_all(self.transcript_dir, self.metas)

    def ensure(self, session_id: str) -> SessionMeta:
        meta = get_or_create(self.metas, session_id)
        return meta

    def ensure_saved(self, session_id: str) -> SessionMeta:
        meta = self.ensure(session_id)
        self.save()
        return meta

    def increment_user_turn(self, session_id: str) -> int:
        turn_no = increment_user_turn(self.metas, session_id)
        self.save()
        return turn_no

    def set_title(self, session_id: str, *, title: str, title_gen_turn: int) -> None:
        set_title(self.metas, session_id, title=title, title_gen_turn=title_gen_turn)
        self.save()

    def clear_session(self, session_id: str) -> None:
        self.metas[session_id] = SessionMeta(session_id=session_id)
        self.save()

    def list_sessions(self, defaults: DefaultSessions) -> list[str]:
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

    def first_user_message(self, session_id: str) -> str | None:
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

    def title_for_list(self, session_id: str) -> str:
        meta = self.metas.get(session_id)
        if meta is not None and meta.title:
            return meta.title
        first = self.first_user_message(session_id)
        if first:
            first = " ".join(first.strip().split())
            return first[:60] + ("..." if len(first) > 60 else "")
        return "Untitled"