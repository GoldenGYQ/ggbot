from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable
import os
import time

from pydantic import BaseModel, Field

from ..core.workspace_manager import get_workspace_manager, PermissionError
from .registry import tool
from .job_store import JobRecord, jobs_dir, new_job_id, upsert_job


class ShellRunArgs(BaseModel):
    command: str = Field(..., description="Shell command to run")
    background: bool = Field(
        False,
        description="If true, start command in background and return a job_id instead of waiting for completion.",
    )


def _truncate(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    return s[:limit] + f"\n…(truncated, {len(s) - limit} chars omitted)"


def _extract_paths_from_command(command: str, workspace_root: Path) -> list[Path]:
    """从shell命令中提取路径并检查是否在允许的工作区内"""
    import shlex
    from pathlib import Path

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


ConfirmCallback = Callable[[str], str | None]


def make_shell_tool(
    *,
    workspace_root: Path,
    confirm: bool,
    timeout_ms: int,
    max_output_chars: int,
    confirm_callback: ConfirmCallback | None = None,
):
    @tool()
    def shell_run(args: ShellRunArgs) -> str:
        """Run a shell command in workspace_root. Use carefully."""
        # 验证命令中的路径是否在允许的工作区内
        try:
            _validate_command_paths(args.command, workspace_root)
        except PermissionError as e:
            return f"权限错误: {e}"

        if confirm:
            if confirm_callback is not None:
                cancel_reason = confirm_callback(args.command)
                if cancel_reason is not None:
                    return cancel_reason
            else:
                answer = input(f"Allow shell_run? `{args.command}` [y/N]: ").strip().lower()
                if answer not in {"y", "yes"}:
                    return "Cancelled by user."

        if args.background:
            job_id = new_job_id()
            job_root = jobs_dir(workspace_root=workspace_root)
            job_root.mkdir(parents=True, exist_ok=True)
            log_path = (job_root / f"{job_id}.log").resolve()
            started_ms = int(time.time() * 1000)

            # Use a real file handle so the child can keep writing after we return.
            f = log_path.open("a", encoding="utf-8", errors="replace")
            try:
                creationflags = 0
                if os.name == "nt":
                    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

                proc = subprocess.Popen(
                    args.command,
                    cwd=str(workspace_root),
                    shell=True,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    text=True,
                    creationflags=creationflags,
                )
            except Exception:
                f.close()
                raise

            record = JobRecord(
                job_id=job_id,
                pid=int(proc.pid),
                command=args.command,
                cwd=str(workspace_root),
                log_path=str(log_path),
                started_ms=started_ms,
                status="running",
            )
            upsert_job(workspace_root=workspace_root, record=record)
            return (
                f"Started background job {job_id} (pid={proc.pid}).\n"
                f"Log: {log_path}\n"
                "Use shell_tail(job_id=...) to read output and shell_kill(job_id=...) to stop."
            )

        completed = subprocess.run(
            args.command,
            cwd=str(workspace_root),
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_ms / 1000,
        )

        out = (completed.stdout or "") + (completed.stderr or "")
        out = _truncate(out, max_output_chars)
        return f"exit_code={completed.returncode}\n{out}".strip()

    return shell_run
