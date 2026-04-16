from __future__ import annotations

from ..domain.domain import RuntimeEventType
from ..transport.transcript_contract import TranscriptEventType

# Domain event type -> transcript event type.
DOMAIN_TO_TRANSCRIPT_EVENT_TYPE_MAP: dict[RuntimeEventType, TranscriptEventType] = {
    "request": "model_message",
    "response": "model_message",
    "event": "model_message",
    "status": "status",
    "error": "provider_error",
    "tool_call": "tool_call",
    "tool_result": "tool_result",
    "assistant_delta": "model_message",
    "assistant_final": "model_message",
    "thinking": "thinking",
    "turn_update": "turn_update",
    "turn_complete": "turn_complete",
    "session_update": "status",
    "permission_request": "status",
    "permission_response": "status",
}
