from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable
import os
import time

from pydantic import BaseModel, Field

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
