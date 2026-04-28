from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable
import os
import time
import re

from pydantic import BaseModel, Field

from ..workspace.workspace_manager import get_workspace_manager, PermissionError
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

    paths = []

    def _is_shell_operator(token: str) -> bool:
        return token in {"&&", "||", "|", ";", "&", ">", ">>", "<", "<<", "2>", "1>", "2>&1"}

    def _is_windows_switch(token: str) -> bool:
        # e.g. /B, /S, /A:D
        return bool(re.match(r"^/[A-Za-z][A-Za-z0-9:,-]*$", token))

    def _looks_like_path_token(token: str) -> bool:
        if not token:
            return False
        if token.startswith("~") or token.startswith("."):
            return True
        if token.startswith("/") and not _is_windows_switch(token):
            return True
        if "\\" in token:
            return True
        if "/" in token:
            return True
        suffix = Path(token).suffix
        if suffix and any(ch.isalpha() for ch in suffix[1:]):
            return True
        return False

    def _to_candidate_path(token: str) -> Path:
        p = Path(token)
        if p.is_absolute():
            return p.resolve()
        return (workspace_root / p).resolve()

    try:
        parts = shlex.split(command, posix=(os.name != "nt"))
        expect_executable = True
        i = 0
        while i < len(parts):
            part = parts[i]
            if not part:
                i += 1
                continue

            if _is_shell_operator(part):
                expect_executable = True
                i += 1
                continue

            # 每个子命令的第一个 token 视为可执行程序，允许不在工作区内。
            if expect_executable:
                expect_executable = False
                lower = part.lower()
                if lower in {"cd", "chdir", "pushd"} and i + 1 < len(parts):
                    target = parts[i + 1]
                    if target and not target.startswith("-") and not _is_windows_switch(target):
                        try:
                            paths.append(_to_candidate_path(target))
                        except Exception:
                            pass
                    i += 2
                    continue
                i += 1
                continue

            # 跳过常见参数形式，尤其是 Windows 的 /B /S 这类开关。
            if part.startswith("-") or _is_windows_switch(part):
                i += 1
                continue

            if _looks_like_path_token(part):
                try:
                    paths.append(_to_candidate_path(part))
                except Exception:
                    pass
            i += 1
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
