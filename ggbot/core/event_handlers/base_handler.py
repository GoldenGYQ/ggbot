from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..domain import (
    PermissionDecision,
    RuntimeEvent,
    SessionState,
    ToolCall,
    ToolFunction,
    ToolResult,
    create_assistant_delta_event,
    create_assistant_final_event,
    create_permission_request_event,
    create_permission_response_event,
    create_session_update_event,
    create_thinking_event,
    create_tool_call_event,
    create_tool_result_event,
    create_turn_complete_event,
    create_turn_update_event,
)
from ..event_bus import EventBus, EventHandler, publish_event
from ..types import ToolCall as CoreToolCall


def _normalize_assistant_delta_payload(data: dict[str, Any]) -> dict[str, str]:
    return {"delta": str(data.get("delta") or "")}


def _normalize_assistant_final_payload(data: dict[str, Any]) -> dict[str, str]:
    return {"content": str(data.get("content") or "")}


def _normalize_thinking_payload(data: dict[str, Any]) -> dict[str, str]:
    return {"thinking": str(data.get("thinking") or "")}


def _normalize_turn_update_payload(data: dict[str, Any]) -> dict[str, int]:
    return {
        "current_turn": int(data.get("current_turn") or 0),
        "max_turns": int(data.get("max_turns") or 0),
    }


def _normalize_turn_complete_payload(data: dict[str, Any]) -> dict[str, int]:
    return {"turns_used": int(data.get("turns_used") or 0)}


def _normalize_error_payload(data: dict[str, Any]) -> dict[str, str]:
    return {"error": str(data.get("error") or "Unknown error")}


def _normalize_status_payload(data: dict[str, Any]) -> dict[str, str]:
    return {"message": str(data.get("message") or "")}


def _normalize_permission_request_payload(data: dict[str, Any]) -> dict[str, Any]:
    args = data.get("arguments")
    if not isinstance(args, dict):
        args = {}
    return {
        "tool_name": str(data.get("tool_name") or ""),
        "arguments": args,
    }


def _coerce_tool_call(tool_call: ToolCall | CoreToolCall | dict[str, Any]) -> ToolCall:
    if isinstance(tool_call, ToolCall):
        return tool_call

    if isinstance(tool_call, CoreToolCall):
        return ToolCall(
            id=tool_call.id,
            type=tool_call.type,
            function=ToolFunction(
                name=tool_call.function.name,
                arguments=tool_call.function.arguments,
            ),
        )

    if isinstance(tool_call, dict):
        tool_id = str(tool_call.get("id") or "")
        tool_type = str(tool_call.get("type") or "function")
        fn = tool_call.get("function") or {}
        if isinstance(fn, dict):
            fn_name = str(fn.get("name") or tool_call.get("name") or "unknown")
            fn_args = str(fn.get("arguments") or "")
        else:
            fn_name = str(tool_call.get("name") or "unknown")
            fn_args = ""
        return ToolCall(id=tool_id, type=tool_type, function=ToolFunction(name=fn_name, arguments=fn_args))

    raise TypeError(f"Unsupported tool_call type: {type(tool_call).__name__}")


def _coerce_tool_result(tool_result: ToolResult | dict[str, Any]) -> ToolResult:
    if isinstance(tool_result, ToolResult):
        return tool_result

    if isinstance(tool_result, dict):
        tool_call_id = str(tool_result.get("tool_call_id") or tool_result.get("id") or "")
        return ToolResult(
            tool_call_id=tool_call_id,
            name=str(tool_result.get("name") or "unknown"),
            content=str(tool_result.get("content") or ""),
            error=bool(tool_result.get("error", False)),
            auto_healed=bool(tool_result.get("auto_healed", False)),
        )

    raise TypeError(f"Unsupported tool_result type: {type(tool_result).__name__}")


@dataclass
class AgentState:
    """In-memory event-driven agent state."""

    session_id: str = ""
    title: str = "Untitled"
    user_turns: int = 0
    current_turn: int = 0
    max_turns: int = 8
    thinking_enabled: bool = False
    status_updates: list[str] = field(default_factory=list)

    def update_from_session_state(self, session_state: SessionState) -> None:
        self.session_id = session_state.session_id
        self.title = session_state.title
        self.user_turns = session_state.user_turns
        self.current_turn = session_state.current_turn
        self.max_turns = session_state.max_turns
        self.thinking_enabled = session_state.thinking_enabled

    def add_status_update(self, message: str) -> None:
        if message:
            self.status_updates.append(message)
            if len(self.status_updates) > 3:
                self.status_updates = self.status_updates[-3:]

    def to_session_state(self) -> SessionState:
        return SessionState(
            session_id=self.session_id,
            title=self.title,
            user_turns=self.user_turns,
            current_turn=self.current_turn,
            max_turns=self.max_turns,
            thinking_enabled=self.thinking_enabled,
        )


class BaseEventHandler(EventHandler):
    """Business-side event handler that updates state and emits derived events."""

    def __init__(self, event_bus: EventBus | None = None):
        super().__init__(event_bus=event_bus)
        self.state = AgentState()
        self._setup_subscriptions()

    def _setup_subscriptions(self) -> None:
        @self.subscribe(["assistant_delta"])
        def on_assistant_delta(event: RuntimeEvent) -> None:
            delta = _normalize_assistant_delta_payload(event.data)["delta"]
            self._handle_assistant_delta(delta)

        @self.subscribe(["assistant_final"])
        def on_assistant_final(event: RuntimeEvent) -> None:
            content = _normalize_assistant_final_payload(event.data)["content"]
            self._handle_assistant_final(content)

        @self.subscribe(["tool_call"])
        def on_tool_call(event: RuntimeEvent) -> None:
            self._handle_tool_call(event.data)

        @self.subscribe(["tool_result"])
        def on_tool_result(event: RuntimeEvent) -> None:
            self._handle_tool_result(event.data)

        @self.subscribe(["thinking"])
        def on_thinking(event: RuntimeEvent) -> None:
            thinking = _normalize_thinking_payload(event.data)["thinking"]
            self._handle_thinking(thinking)

        @self.subscribe(["turn_update"])
        def on_turn_update(event: RuntimeEvent) -> None:
            payload = _normalize_turn_update_payload(event.data)
            self._handle_turn_update(payload["current_turn"], payload["max_turns"])

        @self.subscribe(["turn_complete"])
        def on_turn_complete(event: RuntimeEvent) -> None:
            turns_used = _normalize_turn_complete_payload(event.data)["turns_used"]
            self._handle_turn_complete(turns_used)

        @self.subscribe(["session_update"])
        def on_session_update(event: RuntimeEvent) -> None:
            self._handle_session_update(event.data)

        @self.subscribe(["error"])
        def on_error(event: RuntimeEvent) -> None:
            error_msg = _normalize_error_payload(event.data)["error"]
            self._handle_error(error_msg)

        @self.subscribe(["status"])
        def on_status(event: RuntimeEvent) -> None:
            status_msg = _normalize_status_payload(event.data)["message"]
            self._handle_status(status_msg)

        @self.subscribe(["permission_request"])
        def on_permission_request(event: RuntimeEvent) -> None:
            payload = _normalize_permission_request_payload(event.data)
            self._handle_permission_request(payload["tool_name"], payload["arguments"])

    def _handle_assistant_delta(self, delta: str) -> None:
        pass

    def _handle_assistant_final(self, content: str) -> None:
        pass

    def _handle_tool_call(self, tool_call_data: dict[str, Any]) -> None:
        pass

    def _handle_tool_result(self, tool_result_data: dict[str, Any]) -> None:
        name = str(tool_result_data.get("name") or "unknown")
        content = str(tool_result_data.get("content") or "")

        if name == "status_update":
            self.state.add_status_update(content)
            self.publish_status({"message": content})

    def _handle_thinking(self, thinking: str) -> None:
        pass

    def _handle_turn_update(self, current_turn: int, max_turns: int) -> None:
        self.state.current_turn = current_turn
        self.state.max_turns = max_turns

    def _handle_turn_complete(self, turns_used: int) -> None:
        self.state.current_turn = turns_used

    def _handle_session_update(self, session_data: dict[str, Any]) -> None:
        self.state.update_from_session_state(SessionState(**session_data))

    def _handle_error(self, error_msg: str) -> None:
        pass

    def _handle_status(self, status_msg: str) -> None:
        self.state.add_status_update(status_msg)

    def _handle_permission_request(self, tool_name: str, arguments: dict[str, Any]) -> None:
        pass

    @staticmethod
    def publish_assistant_delta(delta: str) -> None:
        publish_event(create_assistant_delta_event(delta))

    @staticmethod
    def publish_assistant_final(content: str) -> None:
        publish_event(create_assistant_final_event(content))

    @staticmethod
    def publish_tool_call(tool_call: ToolCall | CoreToolCall | dict[str, Any]) -> None:
        publish_event(create_tool_call_event(_coerce_tool_call(tool_call)))

    @staticmethod
    def publish_tool_result(tool_result: ToolResult | dict[str, Any]) -> None:
        publish_event(create_tool_result_event(_coerce_tool_result(tool_result)))

    @staticmethod
    def publish_thinking(thinking: str) -> None:
        publish_event(create_thinking_event(thinking))

    @staticmethod
    def publish_turn_update(current_turn: int, max_turns: int) -> None:
        publish_event(create_turn_update_event(current_turn, max_turns))

    @staticmethod
    def publish_turn_complete(turns_used: int) -> None:
        publish_event(create_turn_complete_event(turns_used))

    @staticmethod
    def publish_session_update(session_state: SessionState) -> None:
        publish_event(create_session_update_event(session_state))

    @staticmethod
    def publish_permission_request(tool_name: str, arguments: dict[str, Any]) -> None:
        publish_event(create_permission_request_event(tool_name, arguments))

    @staticmethod
    def publish_permission_response(
        allowed: bool | PermissionDecision,
        reason: str = "",
        tool_name: str = "",
        arguments: dict[str, Any] | None = None,
    ) -> None:
        if isinstance(allowed, PermissionDecision):
            decision = allowed
        else:
            decision = PermissionDecision(
                allowed=allowed,
                reason=reason,
                tool_name=tool_name,
                arguments=arguments or {},
            )
        publish_event(create_permission_response_event(decision))

    @staticmethod
    def publish_ui_event(payload: dict[str, Any]) -> None:
        publish_event(RuntimeEvent(type="event", data={"ui_event": payload}))

    @staticmethod
    def publish_status(data: dict[str, Any]) -> None:
        publish_event(RuntimeEvent(type="status", data=data))

    @staticmethod
    def publish_error(data: dict[str, Any]) -> None:
        publish_event(RuntimeEvent(type="error", data=data))


def create_base_event_handler(event_bus: EventBus | None = None) -> BaseEventHandler:
    return BaseEventHandler(event_bus=event_bus)
