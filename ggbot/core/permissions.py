from __future__ import annotations

from pathlib import Path


class PermissionError(Exception):
    pass


def ensure_under_root(root: Path, path: Path) -> Path:
    root_resolved = root.resolve()
    path_resolved = path.resolve()
    try:
        path_resolved.relative_to(root_resolved)
    except ValueError as e:
        raise PermissionError(f"Path not under workspace_root: {path_resolved}") from e
    return path_resolved
