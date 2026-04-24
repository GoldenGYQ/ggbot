from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from ggbot.api.permission_manager import PermissionManager
from ggbot.state.transcript import Transcript
from ggbot.models.runtime_models import RuntimeEvent


def test_permission_manager_request_and_resolve() -> None:
    manager = PermissionManager(default_timeout_s=1.0)

    events: list[RuntimeEvent] = []
    result_holder: dict[str, object] = {}

    def worker() -> None:
        worker_token = manager.set_request_context(
            connection_id="conn-1",
            session_id="session-1",
            event_callback=lambda event: events.append(event),
        )
        try:
            allowed, reason, request_id = manager.request(
                tool_name="shell_run",
                arguments={"command": "echo hi"},
                timeout_s=1.0,
            )
            result_holder["allowed"] = allowed
            result_holder["reason"] = reason
            result_holder["request_id"] = request_id
        finally:
            manager.reset_request_context(worker_token)

    t = threading.Thread(target=worker)
    t.start()

    deadline = time.time() + 1.0
    request_id = None
    while time.time() < deadline:
        for event in events:
            if event.type == "permission_request":
                request_id = event.data.get("request_id")
                break
        if request_id:
            break
        time.sleep(0.01)

    assert request_id is not None
    assert manager.resolve(
        request_id=request_id,
        allowed=True,
        reason="approved",
        actor_connection_id="conn-1",
        actor_session_id="session-1",
    ) is True

    t.join(timeout=2.0)
    assert result_holder["allowed"] is True
    assert result_holder["reason"] == "approved"
    assert any(ev.type == "permission_response" and ev.data.get("allowed") is True for ev in events)


def test_permission_manager_timeout_denies() -> None:
    manager = PermissionManager(default_timeout_s=0.02)
    allowed, reason, _ = manager.request(
        tool_name="shell_run",
        arguments={"command": "echo hi"},
        timeout_s=0.02,
    )
    assert allowed is False
    assert "timed out" in reason


def test_permission_manager_writes_permission_events_to_request_transcript(tmp_path: Path) -> None:
    manager = PermissionManager(default_timeout_s=1.0)
    transcript = Transcript(path=tmp_path / "permission.jsonl")

    emitted: list[RuntimeEvent] = []
    result_holder: dict[str, object] = {}

    def worker() -> None:
        token = manager.set_request_context(
            connection_id="conn-1",
            session_id="session-1",
            user_id=None,
            event_callback=lambda event: emitted.append(event),
            transcript=transcript,
        )
        try:
            allowed, reason, request_id = manager.request(
                tool_name="shell_run",
                arguments={"command": "echo hi"},
                timeout_s=1.0,
            )
            result_holder["allowed"] = allowed
            result_holder["reason"] = reason
            result_holder["request_id"] = request_id
        finally:
            manager.reset_request_context(token)

    t = threading.Thread(target=worker)
    t.start()

    deadline = time.time() + 1.0
    request_id = None
    while time.time() < deadline:
        for event in emitted:
            if event.type == "permission_request":
                request_id = event.data.get("request_id")
                break
        if request_id:
            break
        time.sleep(0.01)

    assert request_id is not None
    assert manager.resolve(
        request_id=request_id,
        allowed=True,
        reason="approved",
        actor_connection_id="conn-1",
        actor_session_id="session-1",
    ) is True

    t.join(timeout=2.0)
    assert result_holder["allowed"] is True
    assert len(emitted) == 2
    assert emitted[0].type == "permission_request"
    assert emitted[1].type == "permission_response"

    lines = [json.loads(line) for line in transcript.path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [line["data"]["_event_type"] for line in lines] == ["permission_request", "permission_response"]
