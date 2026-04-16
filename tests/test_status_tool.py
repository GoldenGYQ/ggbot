from __future__ import annotations

from pathlib import Path

from ggbot.state.transcript import Transcript
from ggbot.tools.context import ToolContext
from ggbot.tools.registry import ToolRegistry
from ggbot.tools.status_tool import make_status_tool


def test_status_update_appends_status_event(tmp_path: Path) -> None:
    transcript = Transcript(path=tmp_path / "t.jsonl")

    reg = ToolRegistry()
    status_update = make_status_tool()
    reg.register_tool(status_update)

    ctx = ToolContext(session_id="s1", transcript=transcript, workspace_root=tmp_path)
    out = reg.call(
        "status_update",
        {"message": "Working...", "stage": "run", "percent": 5},
        ctx=ctx,
    )

    assert out == "[run] 5% Working..."

    events = list(transcript.iter_events())
    assert any(ev.get("type") == "status" and (ev.get("data") or {}).get("message") == "Working..." for ev in events)
