from __future__ import annotations

import re
from pathlib import Path

from typer.testing import CliRunner

from ggbot.cli import app
from ggbot.state.transcript import Transcript
from ggbot.models.protocol_models import ChatMessage


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI escape codes from text."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


def test_log_command_shows_messages_for_session(tmp_path: Path) -> None:
    transcript_dir = tmp_path / ".ggbot" / "transcripts"
    transcript = Transcript(path=transcript_dir / "repl.jsonl")
    transcript.append("model_message", ChatMessage(role="user", content="hello").model_dump(exclude_none=True))
    transcript.append("model_message", ChatMessage(role="assistant", content="hi there").model_dump(exclude_none=True))

    runner = CliRunner()
    res = runner.invoke(app, ["log", "--workspace-root", str(tmp_path), "--session", "repl"])

    assert res.exit_code == 0
    assert "GGbot log" in strip_ansi_codes(res.stdout)
    assert "[USER] hello" in strip_ansi_codes(res.stdout)
    assert "[ASSISTANT] hi there" in strip_ansi_codes(res.stdout)


def test_log_command_handles_missing_session(tmp_path: Path) -> None:
    runner = CliRunner()
    res = runner.invoke(app, ["log", "--workspace-root", str(tmp_path), "--session", "does-not-exist"])

    assert res.exit_code == 0
    assert "No transcript found" in res.stdout


def test_log_command_includes_runtime_events_by_default(tmp_path: Path) -> None:
    transcript_dir = tmp_path / ".ggbot" / "transcripts"
    transcript = Transcript(path=transcript_dir / "repl.jsonl")
    transcript.append("tool_call", {"id": "call_1", "name": "workspace_list", "arguments": {"path": "."}})
    transcript.append("tool_result", {"id": "call_1", "name": "workspace_list", "content_len": 12})

    runner = CliRunner()
    res = runner.invoke(app, ["log", "--workspace-root", str(tmp_path), "--session", "repl"])

    assert res.exit_code == 0
    assert "[EVENT] tool_call name=workspace_list" in strip_ansi_codes(res.stdout)
    assert "[EVENT] tool_result name=workspace_list status=ok" in strip_ansi_codes(res.stdout)


def test_log_command_can_disable_runtime_events(tmp_path: Path) -> None:
    transcript_dir = tmp_path / ".ggbot" / "transcripts"
    transcript = Transcript(path=transcript_dir / "repl.jsonl")
    transcript.append("tool_call", {"id": "call_1", "name": "workspace_list", "arguments": {"path": "."}})
    transcript.append("model_message", ChatMessage(role="user", content="hello").model_dump(exclude_none=True))

    runner = CliRunner()
    res = runner.invoke(app, ["log", "--workspace-root", str(tmp_path), "--session", "repl", "--no-events"])

    assert res.exit_code == 0
    assert "[EVENT]" not in strip_ansi_codes(res.stdout)
    assert "[USER] hello" in strip_ansi_codes(res.stdout)


def test_log_command_renders_status_events(tmp_path: Path) -> None:
    transcript_dir = tmp_path / ".ggbot" / "transcripts"
    transcript = Transcript(path=transcript_dir / "repl.jsonl")
    transcript.append("status", {"message": "Working...", "stage": "run", "percent": 5})

    runner = CliRunner()
    res = runner.invoke(app, ["log", "--workspace-root", str(tmp_path), "--session", "repl"])

    assert res.exit_code == 0
    assert "[EVENT] status stage=run percent=5 Working..." in strip_ansi_codes(res.stdout)
