from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

from pydantic import BaseModel, Field

from ..workspace.permissions import ensure_under_root
from .job_store import JobRecord, load_jobs, pid_is_running, save_jobs
from .registry import tool


class ShellJobsArgs(BaseModel):
    pass


class ShellKillArgs(BaseModel):
    job_id: str = Field(..., description="Job id returned by shell_run(background=true)")


class ShellTailArgs(BaseModel):
    job_id: str = Field(..., description="Job id returned by shell_run(background=true)")
    max_chars: int = Field(4000, description="Max characters of log tail to return")


def _truncate(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    return s[:limit] + f"\n…(truncated, {len(s) - limit} chars omitted)"


def make_job_tools(*, workspace_root: Path):
    @tool()
    def shell_jobs(args: ShellJobsArgs) -> str:
        """List background shell jobs started via shell_run(background=true)."""
        jobs = load_jobs(workspace_root=workspace_root)
        if not jobs:
            return "No jobs."

        # Refresh running/exited status best-effort.
        changed = False
        for rec in jobs.values():
            if rec.status == "running" and not pid_is_running(rec.pid):
                rec.status = "exited"
                rec.updated_ms = int(time.time() * 1000)
                changed = True
        if changed:
            save_jobs(workspace_root=workspace_root, jobs=jobs)

        lines = ["job_id\tstatus\tpid\tcommand"]
        for job_id, rec in sorted(jobs.items(), key=lambda kv: kv[0]):
            lines.append(f"{job_id}\t{rec.status}\t{rec.pid}\t{rec.command}")
        return "\n".join(lines)

    @tool()
    def shell_tail(args: ShellTailArgs) -> str:
        """Read the tail of a background job's log."""
        jobs = load_jobs(workspace_root=workspace_root)
        rec = jobs.get(args.job_id)
        if rec is None:
            return f"Unknown job_id: {args.job_id}"

        log_path = ensure_under_root(workspace_root, Path(rec.log_path))
        if not log_path.exists():
            return f"Log not found: {log_path}"

        try:
            text = log_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"Failed to read log: {type(e).__name__}: {e}"

        if args.max_chars <= 0:
            return ""
        tail = text[-args.max_chars :]
        return tail

    @tool()
    def shell_kill(args: ShellKillArgs) -> str:
        """Stop a background job started via shell_run(background=true)."""
        jobs = load_jobs(workspace_root=workspace_root)
        rec = jobs.get(args.job_id)
        if rec is None:
            return f"Unknown job_id: {args.job_id}"

        pid = rec.pid

        if os.name == "nt":
            try:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, timeout=5)
            except Exception as e:
                return f"Failed to kill pid {pid}: {type(e).__name__}: {e}"
        else:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except Exception as e:
                return f"Failed to kill pid {pid}: {type(e).__name__}: {e}"

        rec.status = "killed"
        jobs[args.job_id] = rec
        save_jobs(workspace_root=workspace_root, jobs=jobs)
        return f"Killed {args.job_id} (pid={pid})"

    return shell_jobs, shell_tail, shell_kill
