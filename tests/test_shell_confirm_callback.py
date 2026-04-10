from __future__ import annotations

from pathlib import Path

from ggbot.tools.shell_tool import make_shell_tool


def test_shell_confirm_callback_cancels(tmp_path: Path) -> None:
    shell_run = make_shell_tool(
        workspace_root=tmp_path,
        confirm=True,
        timeout_ms=1000,
        max_output_chars=1000,
        confirm_callback=lambda cmd: "nope",
    )

    reg = getattr(shell_run, "__ggbot_tool__")
    out = reg.handler({"command": "echo hi"})
    assert out == "nope"
