"""Tests for runtime event creation and type validation."""

from __future__ import annotations

import pytest

from ggbot.events.runtime_events import runtime_event, runtime_event_to_transcript_type


@pytest.mark.unit
def test_runtime_event_accepts_domain_event_type() -> None:
    """A valid domain event type (e.g. tool_call) should produce a RuntimeEvent."""
    event = runtime_event("tool_call", {"id": "call_1"})
    assert event.type == "tool_call"
    assert runtime_event_to_transcript_type(event) == "tool_call"


@pytest.mark.unit
def test_runtime_event_rejects_transcript_event_type() -> None:
    """An invalid transcript internal type (e.g. provider_error) should raise ValueError."""
    with pytest.raises(ValueError, match="Unsupported runtime event type"):
        runtime_event("provider_error", {"error": "boom"})

