from __future__ import annotations

from pathlib import Path

import pytest

from ggbot.core.permissions import PermissionError
from ggbot.tools.workspace_tools import make_workspace_tools


def test_create_workspace_creates_base_and_subdirs(tmp_path: Path) -> None:
    create_workspace, _ = make_workspace_tools(workspace_root=tmp_path)
    reg = getattr(create_workspace, "__ggbot_tool__")

    out = reg.handler({"path": "demo", "directories": ["src", "tests/unit"]}, None)

    assert (tmp_path / "demo").is_dir()
    assert (tmp_path / "demo" / "src").is_dir()
    assert (tmp_path / "demo" / "tests" / "unit").is_dir()
    assert "demo" in out


def test_create_workspace_blocks_escape(tmp_path: Path) -> None:
    create_workspace, _ = make_workspace_tools(workspace_root=tmp_path)
    reg = getattr(create_workspace, "__ggbot_tool__")

    with pytest.raises(PermissionError):
        reg.handler({"path": "..\\outside"}, None)


def test_workspace_list_includes_dirs_and_files(tmp_path: Path) -> None:
    (tmp_path / "demo" / "src").mkdir(parents=True)
    (tmp_path / "demo" / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")

    _, workspace_list = make_workspace_tools(workspace_root=tmp_path)
    reg = getattr(workspace_list, "__ggbot_tool__")
    out = reg.handler({"path": "demo", "max_depth": 3, "include_files": True}, None)

    assert "demo/" in out
    assert "src/" in out
    assert "main.py" in out


def test_workspace_list_blocks_escape(tmp_path: Path) -> None:
    _, workspace_list = make_workspace_tools(workspace_root=tmp_path)
    reg = getattr(workspace_list, "__ggbot_tool__")

    with pytest.raises(PermissionError):
        reg.handler({"path": "..\\outside"}, None)
