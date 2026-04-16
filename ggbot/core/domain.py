from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional
from pydantic import BaseModel


# ==================== 领域模型 ====================

@dataclass(frozen=True)
class Message:
    """聊天消息领域模型"""
    role: Literal["system", "user", "assistant", "tool", "thinking"]
    content: Optional[str] = None
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[list[ToolCall]] = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典表示"""
        result: dict[str, Any] = {"role": self.role}
        if self.content is not None:
            result["content"] = self.content
        if self.name is not None:
            result["name"] = self.name
        if self.tool_call_id is not None:
            result["tool_call_id"] = self.tool_call_id
        if self.tool_calls is not None:
            result["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]
        return result


@dataclass(frozen=True)
class ToolCall:
    """工具调用领域模型"""
    id: str
    function: ToolFunction
    type: str = "function"

    def to_dict(self) -> dict[str, Any]:
        """转换为字典表示"""
        return {
            "id": self.id,
            "type": self.type,
            "function": self.function.to_dict()
        }


@dataclass(frozen=True)
class ToolFunction:
    """工具函数领域模型"""
    name: str
    arguments: str

    def to_dict(self) -> dict[str, Any]:
        """转换为字典表示"""
        return {
            "name": self.name,
            "arguments": self.arguments
        }


@dataclass(frozen=True)
class ToolResult:
    """工具执行结果领域模型"""
    tool_call_id: str
    name: str
    content: str
    error: bool = False
    auto_healed: bool = False

    def to_dict(self) -> dict[str, Any]:
        """转换为字典表示"""
        return {
            "tool_call_id": self.tool_call_id,
            "name": self.name,
            "content": self.content,
            "error": self.error,
            "auto_healed": self.auto_healed
        }


@dataclass(frozen=True)
class SessionState:
    """会话状态领域模型"""
    session_id: str
    title: str = "Untitled"
    user_turns: int = 0
    current_turn: int = 0
    max_turns: int = 8
    thinking_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        """转换为字典表示"""
        return {
            "session_id": self.session_id,
            "title": self.title,
            "user_turns": self.user_turns,
            "current_turn": self.current_turn,
            "max_turns": self.max_turns,
            "thinking_enabled": self.thinking_enabled
        }


# ==================== 运行时事件 ====================

RuntimeEventType = Literal[
    "request",
    "response",
    "event",
    "status",
    "error",
    "tool_call",
    "tool_result",
    "assistant_delta",
    "assistant_final",
    "thinking",
    "turn_update",
    "turn_complete",
    "session_update",
    "permission_request",
    "permission_response"
]


@dataclass(frozen=True)
class RuntimeEvent:
    """运行时事件领域模型"""
    type: RuntimeEventType
    data: dict[str, Any] = field(default_factory=dict)
    source: str = "agent_runtime"

    def to_dict(self) -> dict[str, Any]:
        """转换为字典表示"""
        return {
            "type": self.type,
            "data": self.data,
            "source": self.source
        }


# ==================== 权限决策 ====================

@dataclass(frozen=True)
class PermissionDecision:
    """权限决策领域模型"""
    allowed: bool
    reason: str = ""
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典表示"""
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "tool_name": self.tool_name,
            "arguments": self.arguments
        }


# ==================== 工厂函数 ====================

def create_message_event(message: Message) -> RuntimeEvent:
    """创建消息事件"""
    return RuntimeEvent(
        type="event",
        data={
            "message": message.to_dict(),
            "event_type": "model_message"
        }
    )


def create_tool_call_event(tool_call: ToolCall) -> RuntimeEvent:
    """创建工具调用事件"""
    return RuntimeEvent(
        type="tool_call",
        data=tool_call.to_dict()
    )


def create_tool_result_event(tool_result: ToolResult) -> RuntimeEvent:
    """创建工具结果事件"""
    return RuntimeEvent(
        type="tool_result",
        data=tool_result.to_dict()
    )


def create_assistant_delta_event(delta: str) -> RuntimeEvent:
    """创建助手增量输出事件"""
    return RuntimeEvent(
        type="assistant_delta",
        data={"delta": delta}
    )


def create_assistant_final_event(content: str) -> RuntimeEvent:
    """创建助手最终输出事件"""
    return RuntimeEvent(
        type="assistant_final",
        data={"content": content}
    )


def create_thinking_event(thinking: str) -> RuntimeEvent:
    """创建思考事件"""
    return RuntimeEvent(
        type="thinking",
        data={"thinking": thinking}
    )


def create_turn_update_event(current_turn: int, max_turns: int) -> RuntimeEvent:
    """创建轮次更新事件"""
    return RuntimeEvent(
        type="turn_update",
        data={
            "current_turn": current_turn,
            "max_turns": max_turns
        }
    )


def create_turn_complete_event(turns_used: int) -> RuntimeEvent:
    """创建轮次完成事件"""
    return RuntimeEvent(
        type="turn_complete",
        data={"turns_used": turns_used}
    )


def create_session_update_event(session_state: SessionState) -> RuntimeEvent:
    """创建会话更新事件"""
    return RuntimeEvent(
        type="session_update",
        data=session_state.to_dict()
    )


def create_permission_request_event(tool_name: str, arguments: dict[str, Any]) -> RuntimeEvent:
    """创建权限请求事件"""
    return RuntimeEvent(
        type="permission_request",
        data={
            "tool_name": tool_name,
            "arguments": arguments
        }
    )


def create_permission_response_event(decision: PermissionDecision) -> RuntimeEvent:
    """创建权限响应事件"""
    return RuntimeEvent(
        type="permission_response",
        data=decision.to_dict()
    )