from __future__ import annotations

import pytest

from ggbot.core.runtime_events import runtime_event, runtime_event_to_transcript_type


def test_runtime_event_accepts_domain_event_type() -> None:
    event = runtime_event("tool_call", {"id": "call_1"})
    assert event.type == "tool_call"
    assert runtime_event_to_transcript_type(event) == "tool_call"


def test_runtime_event_rejects_transcript_event_type() -> None:
    with pytest.raises(ValueError, match="Unsupported runtime event type"):
        event = runtime_event("provider_error", {"error": "boom"})
