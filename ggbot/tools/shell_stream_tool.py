from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
import shlex

from pydantic import BaseModel, Field

from ..workspace.workspace_manager import get_workspace_manager, PermissionError
from .context import ToolContext
from .registry import tool


class ShellStreamArgs(BaseModel):
    command: str = Field(..., description="Shell command to run")
    timeout_s: float = Field(30.0, ge=0.5, le=300.0, description="Timeout in seconds")
    max_output_chars: int = Field(20_000, ge=1000, le=200_000, description="Max output chars returned")
    emit_every_ms: int = Field(150, ge=50, le=2000, description="Throttle tool_stream events")


def _truncate(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    return s[:limit] + f"\n…(truncated, {len(s) - limit} chars omitted)"


def _extract_paths_from_command(command: str, workspace_root: Path) -> list[Path]:
    """从shell命令中提取路径并检查是否在允许的工作区内"""
    paths = []
    try:
        # 简单的路径提取逻辑
        parts = shlex.split(command)
        for i, part in enumerate(parts):
            # 跳过选项和参数
            if part.startswith('-'):
                continue

            # 第一个 token 通常是可执行程序路径，允许在工作区外。
            if i == 0:
                continue

            # 处理cd命令的目标目录
            if part == 'cd' and i + 1 < len(parts):
                next_part = parts[i + 1]
                try:
                    path = Path(next_part)
                    if path.is_absolute():
                        paths.append(path)
                    else:
                        # 相对路径，相对于当前目录（在shell中执行时会解析）
                        # 这里我们假设当前目录是workspace_root
                        paths.append((workspace_root / path).resolve())
                except Exception:
                    pass

            # 尝试解析为路径
            try:
                path = Path(part)
                if path.is_absolute():
                    paths.append(path)
                else:
                    # 对于相对路径，检查它是否看起来像一个路径（包含路径分隔符或扩展名）
                    if '/' in part or '\\' in part or '.' in part:
                        # 相对路径，相对于workspace_root
                        full_path = (workspace_root / path).resolve()
                        paths.append(full_path)
            except Exception:
                continue
    except Exception:
        # 如果解析失败，返回空列表
        pass

    return paths


def _validate_command_paths(command: str, workspace_root: Path) -> None:
    """验证命令中的路径是否在允许的工作区内"""
    try:
        workspace_manager = get_workspace_manager()
    except RuntimeError:
        workspace_manager = None

    workspace_root = workspace_root.resolve()
    paths = _extract_paths_from_command(command, workspace_root)

    for path in paths:
        if workspace_manager is None:
            try:
                path.resolve().relative_to(workspace_root)
            except ValueError:
                raise PermissionError(
                    f"命令中的路径不在允许的工作区内: {path}\n"
                    f"命令: {command}\n"
                    f"允许的工作区: ."
                )
            continue

        if not workspace_manager.is_allowed_workspace(path):
            # 检查路径是否在允许的工作区的子目录中
            path_in_allowed = False
            for allowed_path in workspace_manager.get_allowed_workspaces():
                try:
                    path.relative_to(allowed_path)
                    path_in_allowed = True
                    break
                except ValueError:
                    continue

            if not path_in_allowed:
                allowed_paths = workspace_manager.get_relative_paths()
                raise PermissionError(
                    f"命令中的路径不在允许的工作区内: {path}\n"
                    f"命令: {command}\n"
                    f"允许的工作区: {', '.join(allowed_paths)}"
                )


def make_shell_stream_tool(*, workspace_root: Path):
    @tool()
    async def shell_stream(ctx: ToolContext, args: ShellStreamArgs) -> str:
        """Run a shell command and emit incremental output as transcript events."""
        # 验证命令中的路径是否在允许的工作区内
        try:
            _validate_command_paths(args.command, workspace_root)
        except PermissionError as e:
            return f"权限错误: {e}"

        ctx.emit(
            "status",
            {
                "message": f"Running: {args.command}",
                "stage": "shell",
            },
        )

        # Use platform shell; stream stdout/stderr combined.
        proc = await asyncio.create_subprocess_shell(
            args.command,
            cwd=str(workspace_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        output_parts: list[str] = []
        last_emit = 0.0

        async def _reader() -> None:
            nonlocal last_emit
            assert proc.stdout is not None
            while True:
                chunk = await proc.stdout.read(1024)
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")
                output_parts.append(text)

                now = time.time() * 1000
                if now - last_emit >= args.emit_every_ms:
                    last_emit = now
                    ctx.emit(
                        "tool_stream",
                        {
                            "name": ctx.tool_name or "shell_stream",
                            "id": ctx.tool_call_id,
                            "chunk": text,
                        },
                    )

        try:
            await asyncio.wait_for(asyncio.gather(_reader(), proc.wait()), timeout=args.timeout_s)
        except asyncio.TimeoutError:
            # Best-effort terminate.
            try:
                proc.kill()
            except Exception:
                pass
            raise TimeoutError(f"shell_stream timed out after {args.timeout_s}s")

        out = "".join(output_parts)
        out = _truncate(out, args.max_output_chars)
        return f"exit_code={proc.returncode}\n{out}".strip()

    return shell_stream
