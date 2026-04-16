from pathlib import Path

import pytest

from ggbot.workspace.permissions import PermissionError, ensure_under_root


def test_ensure_under_root_allows_child(tmp_path: Path):
    root = tmp_path
    p = ensure_under_root(root, root / "a" / "b.txt")
    assert str(p).endswith(str(Path("a") / "b.txt"))


def test_ensure_under_root_blocks_escape(tmp_path: Path):
    root = tmp_path
    outside = tmp_path.parent / "evil.txt"
    with pytest.raises(PermissionError):
        ensure_under_root(root, outside)
