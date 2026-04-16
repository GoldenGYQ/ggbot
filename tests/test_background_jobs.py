import sys
import time
from pathlib import Path

from ggbot.tools.job_store import load_jobs
from ggbot.tools.shell_tool import make_shell_tool
from ggbot.tools.jobs_tool import make_job_tools


def test_shell_run_background_creates_job_and_log(tmp_path: Path) -> None:
    # Use a temp workspace_root so we don't touch real project state.
    ws = tmp_path

    shell_run = make_shell_tool(
        workspace_root=ws,
        confirm=False,
        timeout_ms=1_000,
        max_output_chars=10_000,
        confirm_callback=None,
    )
    shell_run_handler = getattr(shell_run, "__ggbot_tool__").handler

    cmd = f"\"{sys.executable}\" -c \"print('hello-job')\""
    out = shell_run_handler({"command": cmd, "background": True}, None)
    assert "Started background job" in out

    jobs = load_jobs(workspace_root=ws)
    assert jobs, "Expected jobs.json to contain at least one job"

    job_id = next(iter(jobs.keys()))
    rec = jobs[job_id]
    assert rec.command == cmd
    assert rec.log_path

    # Give the child a moment to flush output to the log.
    time.sleep(0.2)
    log_path = Path(rec.log_path)
    assert log_path.exists()

    shell_jobs, shell_tail, shell_kill = make_job_tools(workspace_root=ws)
    shell_tail_handler = getattr(shell_tail, "__ggbot_tool__").handler
    tail = shell_tail_handler({"job_id": job_id, "max_chars": 2000}, None)
    assert "hello-job" in tail
