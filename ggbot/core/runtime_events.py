from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any

from .events import TranscriptEvent, TranscriptEventType, transcript_event


@dataclass(frozen=True)
class RuntimeEvent:
    type: TranscriptEventType
    data: dict[str, Any] = field(default_factory=dict)

    def to_transcript_event(self) -> TranscriptEvent:
        return transcript_event(self.type, self.data)


def runtime_event(event_type: TranscriptEventType, data: dict[str, Any] | None = None) -> RuntimeEvent:
    return RuntimeEvent(type=event_type, data=data or {})


def consume_runtime_events(
    events: list[RuntimeEvent],
    *,
    on_provider_error: Callable[[dict[str, Any]], None] | None = None,
    on_turn_update: Callable[[dict[str, Any]], None] | None = None,
    on_turn_complete: Callable[[dict[str, Any]], None] | None = None,
    on_thinking: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    for event in events:
        if event.type == "provider_error" and on_provider_error is not None:
            on_provider_error(event.data)
        elif event.type == "turn_update" and on_turn_update is not None:
            on_turn_update(event.data)
        elif event.type == "turn_complete" and on_turn_complete is not None:
            on_turn_complete(event.data)
        elif event.type == "thinking" and on_thinking is not None:
            on_thinking(event.data)
