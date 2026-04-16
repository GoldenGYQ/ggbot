from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..models.runtime_models import RuntimeEvent, RuntimeEventType
from .event_mappings import DOMAIN_TO_TRANSCRIPT_EVENT_TYPE_MAP
from ..transport.transcript_contract import TranscriptEventType


def runtime_event_to_transcript_type(event: RuntimeEvent) -> TranscriptEventType:
    """Resolve transcript event type for a domain runtime event."""
    return DOMAIN_TO_TRANSCRIPT_EVENT_TYPE_MAP.get(event.type, "status")


def runtime_event(
    event_type: RuntimeEventType,
    data: dict[str, Any] | None = None,
) -> RuntimeEvent:
    """Create runtime event with domain event types only."""
    if event_type not in DOMAIN_TO_TRANSCRIPT_EVENT_TYPE_MAP:
        raise ValueError(f"Unsupported runtime event type: {event_type}")
    return RuntimeEvent(type=event_type, data=dict(data or {}))


def consume_runtime_events(
    events: list[RuntimeEvent],
    *,
    on_provider_error: Callable[[dict[str, Any]], None] | None = None,
    on_turn_update: Callable[[dict[str, Any]], None] | None = None,
    on_turn_complete: Callable[[dict[str, Any]], None] | None = None,
    on_thinking: Callable[[dict[str, Any]], None] | None = None,
    on_assistant_delta: Callable[[dict[str, Any]], None] | None = None,
    on_assistant_final: Callable[[dict[str, Any]], None] | None = None,
    on_tool_call: Callable[[dict[str, Any]], None] | None = None,
    on_tool_result: Callable[[dict[str, Any]], None] | None = None,
    on_status: Callable[[dict[str, Any]], None] | None = None,
    on_session_update: Callable[[dict[str, Any]], None] | None = None,
    on_permission_request: Callable[[dict[str, Any]], None] | None = None,
    on_permission_response: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    """Consume runtime events and dispatch callbacks."""
    for event in events:
        if event.type == "error" and on_provider_error is not None:
            on_provider_error(event.data)
        elif event.type == "turn_update" and on_turn_update is not None:
            on_turn_update(event.data)
        elif event.type == "turn_complete" and on_turn_complete is not None:
            on_turn_complete(event.data)
        elif event.type == "thinking" and on_thinking is not None:
            on_thinking(event.data)
        elif event.type == "assistant_delta" and on_assistant_delta is not None:
            on_assistant_delta(event.data)
        elif event.type == "assistant_final" and on_assistant_final is not None:
            on_assistant_final(event.data)
        elif event.type == "tool_call" and on_tool_call is not None:
            on_tool_call(event.data)
        elif event.type == "tool_result" and on_tool_result is not None:
            on_tool_result(event.data)
        elif event.type == "status" and on_status is not None:
            on_status(event.data)
        elif event.type == "session_update" and on_session_update is not None:
            on_session_update(event.data)
        elif event.type == "permission_request" and on_permission_request is not None:
            on_permission_request(event.data)
        elif event.type == "permission_response" and on_permission_response is not None:
            on_permission_response(event.data)
