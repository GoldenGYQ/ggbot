from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from ..core.permissions import ensure_under_root
from .registry import tool


class CreateWorkspaceArgs(BaseModel):
    path: str = Field(
        ".",
        description="Workspace path relative to workspace_root to create or initialize.",
    )
    directories: list[str] = Field(
        default_factory=list,
        description="Optional subdirectories (relative to path) to create.",
    )


class WorkspaceListArgs(BaseModel):
    path: str = Field(
        ".",
        description="Workspace path relative to workspace_root to inspect.",
    )
    max_depth: int = Field(
        3,
        ge=0,
        le=10,
        description="Max recursion depth from path.",
    )
    include_files: bool = Field(
        True,
        description="Whether to include files in the listing.",
    )


def make_workspace_tools(*, workspace_root: Path):
    @tool(
        name="create_workspace",
        description="Create a directory structure under workspace_root.",
        input_model=CreateWorkspaceArgs,
    )
    def create_workspace(args: CreateWorkspaceArgs) -> str:
        base = ensure_under_root(workspace_root, workspace_root / args.path)
        base.mkdir(parents=True, exist_ok=True)

        created: list[Path] = [base]
        for rel in args.directories:
            p = ensure_under_root(workspace_root, base / rel)
            p.mkdir(parents=True, exist_ok=True)
            created.append(p)

        rel_paths = [str(p.relative_to(workspace_root)) if p != workspace_root else "." for p in created]
        return "Created workspace paths:\n" + "\n".join(f"- {r}" for r in rel_paths)

    @tool(
        name="workspace_list",
        description="List files and directories under workspace_root.",
        input_model=WorkspaceListArgs,
    )
    def workspace_list(args: WorkspaceListArgs) -> str:
        root = ensure_under_root(workspace_root, workspace_root / args.path)
        if not root.exists():
            return f"Path does not exist: {args.path}"
        if not root.is_dir():
            rel = str(root.relative_to(workspace_root)) if root != workspace_root else "."
            return f"{rel} (file)"

        base_rel = str(root.relative_to(workspace_root)) if root != workspace_root else "."
        lines: list[str] = [f"{base_rel}/"]

        def walk(current: Path, depth: int) -> None:
            if depth > args.max_depth:
                return
            entries = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            for entry in entries:
                rel = entry.relative_to(root)
                indent = "  " * len(rel.parts)
                if entry.is_dir():
                    lines.append(f"{indent}- {entry.name}/")
                    walk(entry, depth + 1)
                elif args.include_files:
                    lines.append(f"{indent}- {entry.name}")

        walk(root, 1)
        return "\n".join(lines)

    return create_workspace, workspace_list
