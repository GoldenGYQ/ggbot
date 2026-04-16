from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

from ..models.protocol_models import ChatMessage


class TranscriptRecord(Protocol):
    @property
    def type(self) -> str:
        ...

    @property
    def data(self) -> dict[str, Any]:
        ...


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass(frozen=True)
class SessionInfo:
    session_id: str
    path: Path


class Transcript:
    def __init__(self, *, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, event_type: str, data: dict[str, Any]) -> None:
        line = {
            "ts_ms": _now_ms(),
            "type": event_type,
            "data": data,
        }
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    def append_event(self, event: TranscriptRecord) -> None:
        self.append(event.type, event.data)

    def iter_events(self) -> Iterable[dict[str, Any]]:
        if not self._path.exists():
            return
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def clear_transcript(transcript: Transcript) -> None:
    transcript.path.write_text("", encoding="utf-8")


def open_session(*, transcript_dir: Path, session_id: str) -> SessionInfo:
    # Prevent path traversal / invalid filenames.
    # Session ids are used as filenames under transcript_dir.
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", session_id):
        raise ValueError(
            "Invalid session_id. Use 1-64 chars of letters, digits, '_' or '-'. "
            f"Got: {session_id!r}"
        )
    transcript_dir.mkdir(parents=True, exist_ok=True)
    path = transcript_dir / f"{session_id}.jsonl"
    return SessionInfo(session_id=session_id, path=path)


def load_model_messages(transcript: Transcript) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    for ev in transcript.iter_events():
        if ev.get("type") != "model_message":
            continue
        data = ev.get("data") or {}
        try:
            messages.append(ChatMessage.model_validate(data))
        except Exception:
            continue
    return messages
