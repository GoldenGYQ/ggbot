from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any

from .events import TranscriptEvent, TranscriptEventType, transcript_event
from .domain import RuntimeEvent as DomainRuntimeEvent


@dataclass(frozen=True)
class RuntimeEvent:
    """向后兼容的运行时事件包装器"""
    type: TranscriptEventType
    data: dict[str, Any] = field(default_factory=dict)

    def to_transcript_event(self) -> TranscriptEvent:
        return transcript_event(self.type, self.data)

    def to_domain_event(self) -> DomainRuntimeEvent:
        """转换为领域事件"""
        # 映射旧的事件类型到新的事件类型
        event_type_map = {
            "model_message": "event",
            "tool_call": "tool_call",
            "tool_result": "tool_result",
            "tool_stream": "event",
            "status": "status",
            "provider_error": "error",
            "thinking": "thinking",
            "turn_info": "event",
            "turn_update": "turn_update",
            "turn_complete": "turn_complete"
        }

        domain_type = event_type_map.get(self.type, "event")
        return DomainRuntimeEvent(
            type=domain_type,  # type: ignore
            data=self.data
        )


def runtime_event(event_type: TranscriptEventType, data: dict[str, Any] | None = None) -> RuntimeEvent:
    return RuntimeEvent(type=event_type, data=data or {})


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
    """消费运行时事件，支持多种事件类型"""
    for event in events:
        # 转换为领域事件以获取统一的事件处理
        domain_event = event.to_domain_event()

        # 根据事件类型调用相应的回调
        if domain_event.type == "error" and on_provider_error is not None:
            on_provider_error(domain_event.data)
        elif domain_event.type == "turn_update" and on_turn_update is not None:
            on_turn_update(domain_event.data)
        elif domain_event.type == "turn_complete" and on_turn_complete is not None:
            on_turn_complete(domain_event.data)
        elif domain_event.type == "thinking" and on_thinking is not None:
            on_thinking(domain_event.data)
        elif domain_event.type == "assistant_delta" and on_assistant_delta is not None:
            on_assistant_delta(domain_event.data)
        elif domain_event.type == "assistant_final" and on_assistant_final is not None:
            on_assistant_final(domain_event.data)
        elif domain_event.type == "tool_call" and on_tool_call is not None:
            on_tool_call(domain_event.data)
        elif domain_event.type == "tool_result" and on_tool_result is not None:
            on_tool_result(domain_event.data)
        elif domain_event.type == "status" and on_status is not None:
            on_status(domain_event.data)
        elif domain_event.type == "session_update" and on_session_update is not None:
            on_session_update(domain_event.data)
        elif domain_event.type == "permission_request" and on_permission_request is not None:
            on_permission_request(domain_event.data)
        elif domain_event.type == "permission_response" and on_permission_response is not None:
            on_permission_response(domain_event.data)
        # 向后兼容：处理旧的事件类型
        elif event.type == "provider_error" and on_provider_error is not None:
            on_provider_error(event.data)
        elif event.type == "turn_update" and on_turn_update is not None:
            on_turn_update(event.data)
        elif event.type == "turn_complete" and on_turn_complete is not None:
            on_turn_complete(event.data)
        elif event.type == "thinking" and on_thinking is not None:
            on_thinking(event.data)
