from pathlib import Path

from ggbot.core.session_store import SessionStore
from ggbot.core.sessions import DefaultSessions
from ggbot.core.transcript import Transcript
from ggbot.core.types import ChatMessage


def test_session_store_roundtrip(tmp_path: Path) -> None:
    store = SessionStore.load(tmp_path)
    store.ensure_saved("repl")
    store.increment_user_turn("repl")
    store.set_title("repl", title="Hello\nWorld", title_gen_turn=1)

    reloaded = SessionStore.load(tmp_path)
    assert reloaded.metas["repl"].user_turns == 1
    assert reloaded.metas["repl"].title == "Hello World"


def test_session_store_lists_defaults_first(tmp_path: Path) -> None:
    defaults = DefaultSessions(chat="chat", repl="repl", tui="tui")
    Transcript(path=tmp_path / "old.jsonl").append(
        "model_message",
        ChatMessage(role="user", content="Old session title").model_dump(exclude_none=True),
    )
    Transcript(path=tmp_path / "chat.jsonl").append(
        "model_message",
        ChatMessage(role="user", content="Chat session").model_dump(exclude_none=True),
    )

    store = SessionStore.load(tmp_path)
    sessions = store.list_sessions(defaults)

    assert sessions[:3] == ["repl", "chat", "tui"]
    assert "old" in sessions
    assert store.title_for_list("old") == "Old session title"


def test_session_store_first_user_message(tmp_path: Path) -> None:
    transcript_path = tmp_path / "thread.jsonl"
    transcript = Transcript(path=transcript_path)
    transcript.append("status", {"message": "ignore me"})
    transcript.append("model_message", ChatMessage(role="user", content="hello there").model_dump(exclude_none=True))

    store = SessionStore.load(tmp_path)
    assert store.first_user_message("thread") == "hello there"
    assert store.title_for_list("thread") == "hello there"
