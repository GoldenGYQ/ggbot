from __future__ import annotations

import json

import pytest

from ggbot.events.runtime_events import runtime_event
from ggbot.transport.transport_protocol import (
    TRANSPORT_PROTOCOL_VERSION,
    decode_transport_envelope,
    encode_envelopes_as_ndjson,
    encode_runtime_events,
)


def test_encode_runtime_events_generates_monotonic_seq() -> None:
    events = [
        runtime_event("event", {"max_turns": 4, "start_turn": 0}),
        runtime_event("turn_update", {"current_turn": 1, "max_turns": 4}),
        runtime_event("turn_complete", {"turns_used": 1, "max_turns": 4, "completed": True}),
    ]

    ts_values = iter([1000, 1001, 1002])
    envelopes = encode_runtime_events(
        session_id="abc123",
        events=events,
        start_seq=7,
        source="query_loop",
        ts_ms_factory=lambda: next(ts_values),
    )

    assert [e.seq for e in envelopes] == [7, 8, 9]
    assert [e.ts_ms for e in envelopes] == [1000, 1001, 1002]
    assert all(e.version == TRANSPORT_PROTOCOL_VERSION for e in envelopes)
    assert envelopes[1].event_type == "turn_update"
    assert envelopes[1].data["current_turn"] == 1


def test_encode_envelopes_as_ndjson_roundtrip() -> None:
    envelopes = encode_runtime_events(
        session_id="s1",
        events=[runtime_event("error", {"error": "boom"})],
        ts_ms_factory=lambda: 42,
    )

    text = encode_envelopes_as_ndjson(envelopes)
    lines = [line for line in text.splitlines() if line.strip()]
    assert len(lines) == 1

    wire = json.loads(lines[0])
    restored = decode_transport_envelope(wire)
    assert restored.session_id == "s1"
    assert restored.seq == 1
    assert restored.ts_ms == 42
    assert restored.event_type == "provider_error"
    assert restored.data["error"] == "boom"


def test_decode_transport_envelope_rejects_unknown_version() -> None:
    payload = {
        "version": 999,
        "session_id": "s1",
        "seq": 1,
        "ts_ms": 1,
        "source": "query_loop",
        "event_type": "turn_info",
        "data": {},
    }

    with pytest.raises(ValueError, match="Unsupported transport protocol version"):
        decode_transport_envelope(payload)
