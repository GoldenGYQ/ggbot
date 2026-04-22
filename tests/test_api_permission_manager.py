from __future__ import annotations

import threading
import time

from ggbot.api.permission_manager import PermissionManager
from ggbot.events.event_bus import get_global_event_bus, subscribe_to_events


def test_permission_manager_request_and_resolve() -> None:
    manager = PermissionManager(default_timeout_s=1.0)

    events: list[tuple[str, dict]] = []
    bus = get_global_event_bus()
    sub = subscribe_to_events(lambda e: events.append((e.type, e.data)), ["permission_request", "permission_response"])

    result_holder: dict[str, object] = {}

    def worker() -> None:
        allowed, reason, request_id = manager.request(
            tool_name="shell_run",
            arguments={"command": "echo hi"},
            timeout_s=1.0,
        )
        result_holder["allowed"] = allowed
        result_holder["reason"] = reason
        result_holder["request_id"] = request_id

    try:
        t = threading.Thread(target=worker)
        t.start()

        deadline = time.time() + 1.0
        request_id = None
        while time.time() < deadline:
            for event_type, data in events:
                if event_type == "permission_request":
                    request_id = data.get("request_id")
                    break
            if request_id:
                break
            time.sleep(0.01)

        assert request_id is not None
        assert manager.resolve(request_id=request_id, allowed=True, reason="approved") is True

        t.join(timeout=2.0)
        assert result_holder["allowed"] is True
        assert result_holder["reason"] == "approved"

        assert any(ev[0] == "permission_response" and ev[1].get("allowed") is True for ev in events)
    finally:
        bus.unsubscribe(sub)


def test_permission_manager_timeout_denies() -> None:
    manager = PermissionManager(default_timeout_s=0.02)
    allowed, reason, _ = manager.request(
        tool_name="shell_run",
        arguments={"command": "echo hi"},
        timeout_s=0.02,
    )
    assert allowed is False
    assert "timed out" in reason
