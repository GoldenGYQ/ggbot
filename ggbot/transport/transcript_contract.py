from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


TranscriptEventType = Literal[
    "model_message",
    "tool_call",
    "tool_result",
    "tool_stream",
    "provider_chunk",
    "status",
    "provider_error",
    "thinking",
    "turn_info",
    "turn_update",
    "turn_complete",
]


@dataclass(frozen=True)
class TranscriptEvent:
    type: TranscriptEventType
    data: dict[str, Any] = field(default_factory=dict)


def transcript_event(event_type: TranscriptEventType, data: dict[str, Any] | None = None) -> TranscriptEvent:
    return TranscriptEvent(type=event_type, data=data or {})
