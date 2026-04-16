from pathlib import Path

from ggbot.state.session_meta import (
    get_or_create,
    increment_user_turn,
    load_all,
    save_all,
    set_title,
)


def test_session_meta_roundtrip(tmp_path: Path) -> None:
    metas = {}
    increment_user_turn(metas, "repl")
    set_title(metas, "repl", title="Hello   World\nSecond line", title_gen_turn=1)

    save_all(tmp_path, metas)
    loaded = load_all(tmp_path)
    assert "repl" in loaded
    assert loaded["repl"].user_turns == 1
    # Sanitized: single line + collapsed whitespace.
    assert loaded["repl"].title == "Hello World Second line"


def test_session_meta_get_or_create_defaults(tmp_path: Path) -> None:
    metas = {}
    meta = get_or_create(metas, "chat")
    assert meta.session_id == "chat"
    assert meta.title
