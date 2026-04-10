from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .context import ToolContext
from .registry import tool


class StatusUpdateArgs(BaseModel):
    message: str = Field(..., min_length=1, description="Short status message")
    stage: str | None = Field(None, description="Optional stage label, e.g. plan/run/verify")
    percent: int | None = Field(None, ge=0, le=100, description="Optional progress percentage")
    details: dict[str, Any] | None = Field(None, description="Optional structured details")


def make_status_tool():
    @tool()
    def status_update(ctx: ToolContext, args: StatusUpdateArgs) -> str:
        """Record a runtime status update event for better progress visibility."""

        payload: dict[str, Any] = {
            "message": args.message,
        }
        if args.stage is not None:
            payload["stage"] = args.stage
        if args.percent is not None:
            payload["percent"] = args.percent
        if args.details is not None:
            payload["details"] = args.details
        if ctx.tool_name is not None:
            payload["tool_name"] = ctx.tool_name
        if ctx.tool_call_id is not None:
            payload["tool_call_id"] = ctx.tool_call_id

        ctx.emit("status", payload)

        parts: list[str] = []
        if args.stage:
            parts.append(f"[{args.stage}]")
        if args.percent is not None:
            parts.append(f"{args.percent}%")
        parts.append(args.message)
        return " ".join(parts)

    return status_update
