from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ggbot import _make_api_shell_confirm_callback
from ggbot.tools.shell_tool import _validate_command_paths, make_shell_tool


def test_shell_confirm_callback_cancels(tmp_path: Path) -> None:
    shell_run = make_shell_tool(
        workspace_root=tmp_path,
        confirm=True,
        timeout_ms=1000,
        max_output_chars=1000,
        confirm_callback=lambda cmd: "nope",
    )

    reg = getattr(shell_run, "__ggbot_tool__")
    out = reg.handler({"command": "echo hi"}, None)
    assert out == "nope"


def test_api_shell_confirm_callback_approves(monkeypatch: pytest.MonkeyPatch) -> None:
    logger = MagicMock()
    fake_manager = MagicMock()
    fake_manager.request.return_value = (True, "", "req-1")
    monkeypatch.setattr("ggbot.cli.get_permission_manager", lambda: fake_manager)

    callback = _make_api_shell_confirm_callback(logger)

    out = callback("echo hi")

    assert out is None


def test_validate_command_paths_allows_windows_dir_switch(tmp_path: Path) -> None:
    # Regression: '/B' in `dir /B` should be treated as a switch, not a filesystem path.
    _validate_command_paths("echo GGbot is running! && dir /B", tmp_path)
