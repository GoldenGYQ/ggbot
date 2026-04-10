from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from pydantic import BaseModel, Field

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


def make_shell_stream_tool(*, workspace_root: Path):
    @tool()
    async def shell_stream(ctx: ToolContext, args: ShellStreamArgs) -> str:
        """Run a shell command and emit incremental output as transcript events."""

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
