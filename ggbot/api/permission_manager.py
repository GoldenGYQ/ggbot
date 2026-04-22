from __future__ import annotations

import threading
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from ..events.event_bus import publish_event
from ..models.runtime_models import RuntimeEvent


@dataclass
class PendingPermission:
    request_id: str
    tool_name: str
    arguments: dict[str, Any]
    created_ms: int
    owner_connection_id: str | None = None
    owner_session_id: str | None = None
    owner_user_id: str | None = None
    event: threading.Event = field(default_factory=threading.Event)
    allowed: bool | None = None
    reason: str = ""


class PermissionManager:
    """Thread-safe permission request manager for API mode."""

    def __init__(self, default_timeout_s: float = 300.0):
        self._default_timeout_s = default_timeout_s
        self._lock = threading.Lock()
        self._pending: dict[str, PendingPermission] = {}
        self._request_context: ContextVar[dict[str, str | None]] = ContextVar(
            "permission_request_context",
            default={"connection_id": None, "session_id": None, "user_id": None},
        )

    def set_request_context(
        self,
        *,
        connection_id: str | None,
        session_id: str | None,
        user_id: str | None = None,
    ):
        return self._request_context.set(
            {
                "connection_id": connection_id,
                "session_id": session_id,
                "user_id": user_id,
            }
        )

    def reset_request_context(self, token) -> None:
        self._request_context.reset(token)

    def request(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_s: float | None = None,
    ) -> tuple[bool, str, str]:
        context = self._request_context.get()
        request_id = str(uuid.uuid4())
        pending = PendingPermission(
            request_id=request_id,
            tool_name=tool_name,
            arguments=dict(arguments),
            created_ms=int(time.time() * 1000),
            owner_connection_id=context.get("connection_id"),
            owner_session_id=context.get("session_id"),
            owner_user_id=context.get("user_id"),
        )

        with self._lock:
            self._pending[request_id] = pending

        publish_event(
            RuntimeEvent(
                type="permission_request",
                data={
                    "request_id": request_id,
                    "tool_name": tool_name,
                    "arguments": pending.arguments,
                    "created_ms": pending.created_ms,
                    "session_id": pending.owner_session_id,
                    "user_id": pending.owner_user_id,
                },
                source="api_permission",
            )
        )

        wait_timeout = self._default_timeout_s if timeout_s is None else timeout_s
        pending.event.wait(wait_timeout)

        with self._lock:
            self._pending.pop(request_id, None)

        if pending.allowed is None:
            allowed = False
            reason = "Permission request timed out."
        else:
            allowed = pending.allowed
            reason = pending.reason

        publish_event(
            RuntimeEvent(
                type="permission_response",
                data={
                    "request_id": request_id,
                    "allowed": allowed,
                    "reason": reason,
                    "tool_name": tool_name,
                    "arguments": pending.arguments,
                    "session_id": pending.owner_session_id,
                    "user_id": pending.owner_user_id,
                },
                source="api_permission",
            )
        )

        return allowed, reason, request_id

    def resolve(
        self,
        *,
        request_id: str,
        allowed: bool,
        reason: str = "",
        actor_connection_id: str | None = None,
        actor_session_id: str | None = None,
        actor_user_id: str | None = None,
    ) -> bool:
        with self._lock:
            pending = self._pending.get(request_id)
            if pending is None:
                return False

            if pending.owner_connection_id and actor_connection_id != pending.owner_connection_id:
                return False
            if pending.owner_user_id and actor_user_id != pending.owner_user_id:
                return False
            if pending.owner_session_id and actor_session_id != pending.owner_session_id:
                return False

            pending.allowed = allowed
            pending.reason = reason
            pending.event.set()
            return True


_global_permission_manager: PermissionManager | None = None


def get_permission_manager() -> PermissionManager:
    global _global_permission_manager
    if _global_permission_manager is None:
        _global_permission_manager = PermissionManager()
    return _global_permission_manager
