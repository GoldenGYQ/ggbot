from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from ..core.permissions import ensure_under_root
from .registry import tool


class FileReadArgs(BaseModel):
    path: str = Field(..., description="Path relative to workspace_root")


class FileWriteArgs(BaseModel):
    path: str = Field(..., description="Path relative to workspace_root")
    content: str = Field(..., description="Full file content")


def make_file_tools(*, workspace_root: Path):
    @tool(
        name="file_read",
        description="Read a UTF-8 text file under workspace_root.",
        input_model=FileReadArgs,
    )
    def file_read(args: FileReadArgs) -> str:
        p = ensure_under_root(workspace_root, (workspace_root / args.path))
        return p.read_text(encoding="utf-8")

    @tool(
        name="file_write",
        description="Write a UTF-8 text file under workspace_root (creates parent dirs if needed).",
        input_model=FileWriteArgs,
    )
    def file_write(args: FileWriteArgs) -> str:
        p = ensure_under_root(workspace_root, (workspace_root / args.path))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(args.content, encoding="utf-8")
        return f"Wrote {p} ({len(args.content)} chars)"

    return file_read, file_write
