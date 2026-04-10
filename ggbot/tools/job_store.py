from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class JobRecord:
    job_id: str
    pid: int
    command: str
    cwd: str
    log_path: str
    started_ms: int
    status: str = "running"  # running|exited|killed|unknown
    returncode: int | None = None
    updated_ms: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobRecord":
        rc_raw = data.get("returncode")
        upd_raw = data.get("updated_ms")

        returncode: int | None
        updated_ms: int | None

        try:
            returncode = None if rc_raw is None else int(rc_raw)
        except Exception:
            returncode = None

        try:
            updated_ms = None if upd_raw is None else int(upd_raw)
        except Exception:
            updated_ms = None

        return cls(
            job_id=str(data["job_id"]),
            pid=int(data["pid"]),
            command=str(data.get("command") or ""),
            cwd=str(data.get("cwd") or ""),
            log_path=str(data.get("log_path") or ""),
            started_ms=int(data.get("started_ms") or 0),
            status=str(data.get("status") or "unknown"),
            returncode=returncode,
            updated_ms=updated_ms,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "pid": self.pid,
            "command": self.command,
            "cwd": self.cwd,
            "log_path": self.log_path,
            "started_ms": self.started_ms,
            "status": self.status,
            "returncode": self.returncode,
            "updated_ms": self.updated_ms,
        }


def jobs_dir(*, workspace_root: Path) -> Path:
    return (workspace_root / ".ggbot" / "jobs").resolve()


def jobs_db_path(*, workspace_root: Path) -> Path:
    return jobs_dir(workspace_root=workspace_root) / "jobs.json"


def new_job_id() -> str:
    # Shorter, still unique enough for local usage.
    return "job_" + uuid.uuid4().hex[:12]


def load_jobs(*, workspace_root: Path) -> dict[str, JobRecord]:
    path = jobs_db_path(workspace_root=workspace_root)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}

    out: dict[str, JobRecord] = {}
    for job_id, data in raw.items():
        if not isinstance(job_id, str) or not isinstance(data, dict):
            continue
        try:
            out[job_id] = JobRecord.from_dict(data)
        except Exception:
            continue
    return out


def save_jobs(*, workspace_root: Path, jobs: dict[str, JobRecord]) -> None:
    path = jobs_db_path(workspace_root=workspace_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {job_id: rec.to_dict() for job_id, rec in jobs.items()}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def upsert_job(*, workspace_root: Path, record: JobRecord) -> None:
    jobs = load_jobs(workspace_root=workspace_root)
    jobs[record.job_id] = record
    save_jobs(workspace_root=workspace_root, jobs=jobs)


def _pid_is_running_windows(pid: int) -> bool:
    # Avoid importing psutil; best-effort using tasklist.
    import subprocess

    try:
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception:
        return False

    out = (completed.stdout or "") + (completed.stderr or "")
    return str(pid) in out


def _pid_is_running_posix(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def pid_is_running(pid: int) -> bool:
    if os.name == "nt":
        return _pid_is_running_windows(pid)
    return _pid_is_running_posix(pid)
