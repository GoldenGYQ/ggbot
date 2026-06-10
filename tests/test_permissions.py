"""Tests for workspace path permission enforcement."""

from __future__ import annotations

from pathlib import Path

import pytest

from ggbot.workspace.permissions import PermissionError, ensure_under_root


@pytest.mark.unit
def test_ensure_under_root_allows_child(tmp_path: Path) -> None:
    """A path under the root should be resolved and returned as-is."""
    root = tmp_path
    p = ensure_under_root(root, root / "a" / "b.txt")
    assert str(p).endswith(str(Path("a") / "b.txt"))


@pytest.mark.unit
def test_ensure_under_root_blocks_escape(tmp_path: Path) -> None:
    """A path outside the root should raise PermissionError."""
    root = tmp_path
    outside = tmp_path.parent / "evil.txt"
    with pytest.raises(PermissionError):
        ensure_under_root(root, outside)

