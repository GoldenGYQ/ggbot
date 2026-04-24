from __future__ import annotations

import sys
from pathlib import Path

from ggbot.state.transcript import Transcript
from ggbot.tools.context import ToolContext
from ggbot.tools.registry import ToolRegistry
from ggbot.tools.shell_stream_tool import make_shell_stream_tool


def test_shell_stream_emits_tool_stream_events(tmp_path: Path) -> None:
    # Quick command; should still emit at least one tool_stream chunk.
    cmd = f"\"{sys.executable}\" -c \"print('a'); print('b')\""

    shell_stream = make_shell_stream_tool(workspace_root=tmp_path)

    reg = ToolRegistry()
    reg.register_tool(shell_stream)

    transcript = Transcript(path=tmp_path / "t.jsonl")
    ctx = ToolContext(session_id="s", transcript=transcript, workspace_root=tmp_path)

    out = reg.call(
        "shell_stream",
        {"command": cmd, "timeout_s": 30.0, "emit_every_ms": 50, "max_output_chars": 20000},
        ctx=ctx,
    )

    assert "exit_code=" in out

    events = list(transcript.iter_events())
    chunks = [
        (ev.get("data") or {}).get("chunk")
        for ev in events
        if ev.get("type") == "tool_stream"
    ]

    joined = "".join([c for c in chunks if isinstance(c, str)])
    assert "a" in joined or "b" in joined
