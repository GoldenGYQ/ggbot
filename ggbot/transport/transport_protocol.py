from __future__ import annotations

import json
import time
from dataclasses import dataclass
from collections.abc import Callable
from typing import Any, cast

from .transcript_contract import TranscriptEventType
from ..models.runtime_models import RuntimeEvent
from ..events.runtime_events import runtime_event_to_transcript_type


TRANSPORT_PROTOCOL_VERSION = 1


def _now_ms() -> int:
    return int(time.time() * 1000)


_EVENT_TYPES: set[str] = {
    "model_message",
    "tool_call",
    "tool_result",
    "tool_stream",
    "status",
    "provider_error",
    "thinking",
    "turn_info",
    "turn_update",
    "turn_complete",
}


@dataclass(frozen=True)
class TransportEnvelope:
    version: int
    session_id: str
    seq: int
    ts_ms: int
    source: str
    event_type: TranscriptEventType
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "session_id": self.session_id,
            "seq": self.seq,
            "ts_ms": self.ts_ms,
            "source": self.source,
            "event_type": self.event_type,
            "data": self.data,
        }


def encode_runtime_events(
    *,
    session_id: str,
    events: list[RuntimeEvent],
    start_seq: int = 1,
    source: str = "agent_runtime",
    ts_ms_factory: Callable[[], int] | None = None,
) -> list[TransportEnvelope]:
    if start_seq < 1:
        raise ValueError(f"start_seq must be >= 1, got {start_seq}")

    if not session_id:
        raise ValueError("session_id cannot be empty")

    now = ts_ms_factory or _now_ms

    out: list[TransportEnvelope] = []
    seq = start_seq
    for event in events:
        transcript_type = runtime_event_to_transcript_type(event)
        out.append(
            TransportEnvelope(
                version=TRANSPORT_PROTOCOL_VERSION,
                session_id=session_id,
                seq=seq,
                ts_ms=int(now()),
                source=source,
                event_type=transcript_type,
                data=dict(event.data),
            )
        )
        seq += 1

    return out


def encode_envelopes_as_ndjson(envelopes: list[TransportEnvelope]) -> str:
    lines = [json.dumps(envelope.to_dict(), ensure_ascii=False) for envelope in envelopes]
    return "\n".join(lines) + ("\n" if lines else "")


def decode_transport_envelope(payload: dict[str, Any]) -> TransportEnvelope:
    version = int(payload.get("version") or 0)
    if version != TRANSPORT_PROTOCOL_VERSION:
        raise ValueError(
            f"Unsupported transport protocol version: {version} (expected {TRANSPORT_PROTOCOL_VERSION})"
        )

    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("session_id must be a non-empty string")

    seq = payload.get("seq")
    if not isinstance(seq, int) or seq < 1:
        raise ValueError("seq must be an integer >= 1")

    ts_ms = payload.get("ts_ms")
    if not isinstance(ts_ms, int) or ts_ms < 0:
        raise ValueError("ts_ms must be a non-negative integer")

    source = payload.get("source")
    if not isinstance(source, str) or not source:
        raise ValueError("source must be a non-empty string")

    event_type = payload.get("event_type")
    if not isinstance(event_type, str) or event_type not in _EVENT_TYPES:
        raise ValueError(f"event_type is invalid: {event_type!r}")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("data must be an object")

    return TransportEnvelope(
        version=version,
        session_id=session_id,
        seq=seq,
        ts_ms=ts_ms,
        source=source,
        event_type=cast(TranscriptEventType, event_type),
        data=data,
    )