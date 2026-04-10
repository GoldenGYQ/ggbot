from pathlib import Path

import pytest

from ggbot.core.transcript import Transcript, load_model_messages
from ggbot.core.transcript import open_session
from ggbot.core.types import ChatMessage


def test_transcript_roundtrip(tmp_path: Path) -> None:
    t = Transcript(path=tmp_path / "s.jsonl")
    t.append("model_message", ChatMessage(role="user", content="hi").model_dump(exclude_none=True))
    t.append("model_message", ChatMessage(role="assistant", content="yo").model_dump(exclude_none=True))

    msgs = load_model_messages(t)
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[0].content == "hi"


def test_open_session_rejects_invalid_session_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        open_session(transcript_dir=tmp_path, session_id="../escape")
