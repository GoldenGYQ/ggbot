from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ..transport.transcript_contract import TranscriptEventType, transcript_event
from ..state.transcript import Transcript


@dataclass(frozen=True)
class ToolContext:
    """Runtime context injected into tools.

    This is NOT part of the model-facing tool schema. It's provided by the GGbot
    runtime so tools can access shared capabilities (transcript, sandbox root,
    per-call metadata) without relying on globals.
    """

    session_id: str
    transcript: Transcript
    workspace_root: Path

    # Per-call metadata (populated when executing a specific tool call).
    tool_name: str | None = None
    tool_call_id: str | None = None

    def for_call(self, *, tool_name: str, tool_call_id: str | None) -> ToolContext:
        return replace(self, tool_name=tool_name, tool_call_id=tool_call_id)

    def emit(self, event_type: TranscriptEventType, data: dict[str, Any]) -> None:
        self.transcript.append_event(transcript_event(event_type, data))
