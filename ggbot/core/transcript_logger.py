from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .domain import RuntimeEvent
from .event_bus import EventHandler, subscribe_to_events
from .transcript import Transcript
from .events import transcript_event, TranscriptEventType


class TranscriptLogger(EventHandler):
    """Transcript 事件记录器，确保所有事件都记录到 transcript 中"""

    def __init__(self, transcript: Transcript):
        super().__init__()
        self.transcript = transcript
        self._setup_subscriptions()

    def _setup_subscriptions(self) -> None:
        """设置事件订阅，将所有运行时事件记录到 transcript"""

        # 映射领域事件类型到 transcript 事件类型
        event_type_map = {
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
            "permission_response": "status"
        }

        @self.subscribe(None)  # 订阅所有事件
        def log_all_events(event: RuntimeEvent) -> None:
            """将所有运行时事件记录到 transcript"""
            transcript_type = event_type_map.get(event.type, "status")

            # 准备要记录的数据
            data = dict(event.data)
            data["_event_source"] = event.source
            data["_event_type"] = event.type

            # 特殊处理：将领域事件转换为 transcript 事件
            if event.type in ["request", "response", "event", "assistant_delta", "assistant_final"]:
                # 这些事件需要转换为 model_message
                self._log_as_model_message(event, transcript_type, data)
            else:
                # 其他事件直接记录
                self.transcript.append(transcript_type, data)

    def _log_as_model_message(self, event: RuntimeEvent, transcript_type: str, data: dict[str, Any]) -> None:
        """将领域事件记录为 model_message"""
        # 根据事件类型确定消息角色
        role_map = {
            "request": "user",
            "response": "assistant",
            "event": "system",
            "assistant_delta": "assistant",
            "assistant_final": "assistant"
        }

        role = role_map.get(event.type, "system")

        # 构建消息数据
        message_data = {
            "role": role,
            "content": data.get("content") or data.get("delta") or "",
            "_event_source": event.source,
            "_event_type": event.type
        }

        # 添加工具调用信息（如果有）
        if "tool_calls" in data:
            message_data["tool_calls"] = data["tool_calls"]

        # 添加工具调用ID（如果有）
        if "tool_call_id" in data:
            message_data["tool_call_id"] = data["tool_call_id"]
            message_data["name"] = data.get("name", "unknown")

        self.transcript.append("model_message", message_data)

    def log_runtime_event(self, event: RuntimeEvent) -> None:
        """直接记录运行时事件（向后兼容）"""
        self.transcript.append_event(event.to_transcript_event())

    def log_domain_event(self, event: RuntimeEvent) -> None:
        """记录领域事件"""
        # 通过事件总线发布，让订阅者处理
        from .event_bus import publish_event
        publish_event(event)


def create_transcript_logger(transcript: Transcript) -> TranscriptLogger:
    """创建 transcript 记录器"""
    return TranscriptLogger(transcript)


def ensure_event_logging(transcript: Transcript) -> Callable[[RuntimeEvent], None]:
    """确保事件记录的回调函数（用于向后兼容）"""
    logger = create_transcript_logger(transcript)

    def log_event(event: RuntimeEvent) -> None:
        logger.log_domain_event(event)

    return log_event