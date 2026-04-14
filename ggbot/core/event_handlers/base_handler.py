from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from collections.abc import Callable

from ..domain import (
    RuntimeEvent,
    SessionState,
    ToolCall,
    ToolResult,
    create_assistant_delta_event,
    create_assistant_final_event,
    create_tool_call_event,
    create_tool_result_event,
    create_thinking_event,
    create_turn_update_event,
    create_turn_complete_event,
    create_session_update_event,
    create_permission_request_event,
    create_permission_response_event,
)
from ..event_bus import EventHandler, publish_event


@dataclass
class AgentState:
    """Agent状态管理（业务逻辑）"""
    session_id: str = ""
    title: str = "Untitled"
    user_turns: int = 0
    current_turn: int = 0
    max_turns: int = 8
    thinking_enabled: bool = False
    status_updates: list[str] = field(default_factory=list)

    def update_from_session_state(self, session_state: SessionState) -> None:
        """从SessionState更新状态"""
        self.session_id = session_state.session_id
        self.title = session_state.title
        self.user_turns = session_state.user_turns
        self.current_turn = session_state.current_turn
        self.max_turns = session_state.max_turns
        self.thinking_enabled = session_state.thinking_enabled

    def add_status_update(self, message: str) -> None:
        """添加状态更新"""
        if message:
            self.status_updates.append(message)
            # 保持最近3条
            if len(self.status_updates) > 3:
                self.status_updates = self.status_updates[-3:]

    def to_session_state(self) -> SessionState:
        """转换为SessionState"""
        return SessionState(
            session_id=self.session_id,
            title=self.title,
            user_turns=self.user_turns,
            current_turn=self.current_turn,
            max_turns=self.max_turns,
            thinking_enabled=self.thinking_enabled
        )


class BaseEventHandler(EventHandler):
    """基础事件处理器（业务逻辑）"""

    def __init__(self):
        super().__init__()
        self.state = AgentState()
        self._setup_subscriptions()

    def _setup_subscriptions(self) -> None:
        """设置事件订阅"""

        # 订阅助手增量输出事件
        @self.subscribe(["assistant_delta"])
        def on_assistant_delta(event: RuntimeEvent) -> None:
            delta = event.data.get("delta", "")
            self._handle_assistant_delta(delta)

        # 订阅助手最终输出事件
        @self.subscribe(["assistant_final"])
        def on_assistant_final(event: RuntimeEvent) -> None:
            content = event.data.get("content", "")
            self._handle_assistant_final(content)

        # 订阅工具调用事件
        @self.subscribe(["tool_call"])
        def on_tool_call(event: RuntimeEvent) -> None:
            self._handle_tool_call(event.data)

        # 订阅工具结果事件
        @self.subscribe(["tool_result"])
        def on_tool_result(event: RuntimeEvent) -> None:
            self._handle_tool_result(event.data)

        # 订阅思考事件
        @self.subscribe(["thinking"])
        def on_thinking(event: RuntimeEvent) -> None:
            thinking = event.data.get("thinking", "")
            self._handle_thinking(thinking)

        # 订阅轮次更新事件
        @self.subscribe(["turn_update"])
        def on_turn_update(event: RuntimeEvent) -> None:
            current_turn = event.data.get("current_turn", 0)
            max_turns = event.data.get("max_turns", 8)
            self._handle_turn_update(current_turn, max_turns)

        # 订阅轮次完成事件
        @self.subscribe(["turn_complete"])
        def on_turn_complete(event: RuntimeEvent) -> None:
            turns_used = event.data.get("turns_used", 0)
            self._handle_turn_complete(turns_used)

        # 订阅会话更新事件
        @self.subscribe(["session_update"])
        def on_session_update(event: RuntimeEvent) -> None:
            self._handle_session_update(event.data)

        # 订阅错误事件
        @self.subscribe(["error"])
        def on_error(event: RuntimeEvent) -> None:
            error_msg = event.data.get("error", "Unknown error")
            self._handle_error(error_msg)

        # 订阅状态事件
        @self.subscribe(["status"])
        def on_status(event: RuntimeEvent) -> None:
            status_msg = event.data.get("message", "")
            self._handle_status(status_msg)

        # 订阅权限请求事件
        @self.subscribe(["permission_request"])
        def on_permission_request(event: RuntimeEvent) -> None:
            tool_name = event.data.get("tool_name", "")
            arguments = event.data.get("arguments", {})
            self._handle_permission_request(tool_name, arguments)

    # ==================== 业务逻辑处理方法 ====================

    def _handle_assistant_delta(self, delta: str) -> None:
        """处理助手增量输出（业务逻辑）"""
        # 这里只更新业务状态，不涉及UI渲染
        pass

    def _handle_assistant_final(self, content: str) -> None:
        """处理助手最终输出（业务逻辑）"""
        # 这里只更新业务状态，不涉及UI渲染
        pass

    def _handle_tool_call(self, tool_call_data: dict[str, Any]) -> None:
        """处理工具调用（业务逻辑）"""
        # 这里只更新业务状态，不涉及UI渲染
        pass

    def _handle_tool_result(self, tool_result_data: dict[str, Any]) -> None:
        """处理工具结果（业务逻辑）"""
        name = tool_result_data.get("name", "unknown")
        content = tool_result_data.get("content", "")

        if name == "status_update":
            self.state.add_status_update(content)
            # 发布状态更新事件，让UI渲染
            self.publish_status({"message": content})

    def _handle_thinking(self, thinking: str) -> None:
        """处理思考（业务逻辑）"""
        # 这里只更新业务状态，不涉及UI渲染
        pass

    def _handle_turn_update(self, current_turn: int, max_turns: int) -> None:
        """处理轮次更新（业务逻辑）"""
        self.state.current_turn = current_turn
        self.state.max_turns = max_turns

    def _handle_turn_complete(self, turns_used: int) -> None:
        """处理轮次完成（业务逻辑）"""
        self.state.current_turn = turns_used

    def _handle_session_update(self, session_data: dict[str, Any]) -> None:
        """处理会话更新（业务逻辑）"""
        session_state = SessionState(**session_data)
        self.state.update_from_session_state(session_state)

    def _handle_error(self, error_msg: str) -> None:
        """处理错误（业务逻辑）"""
        # 这里只更新业务状态，不涉及UI渲染
        pass

    def _handle_status(self, status_msg: str) -> None:
        """处理状态（业务逻辑）"""
        self.state.add_status_update(status_msg)

    def _handle_permission_request(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """处理权限请求（业务逻辑）"""
        # 这里只更新业务状态，不涉及UI渲染
        pass

    # ==================== 事件发布方法 ====================

    @staticmethod
    def publish_assistant_delta(delta: str) -> None:
        """发布助手增量输出事件"""
        publish_event(create_assistant_delta_event(delta))

    @staticmethod
    def publish_assistant_final(content: str) -> None:
        """发布助手最终输出事件"""
        publish_event(create_assistant_final_event(content))

    @staticmethod
    def publish_tool_call(tool_call: ToolCall) -> None:
        """发布工具调用事件"""
        publish_event(create_tool_call_event(tool_call))

    @staticmethod
    def publish_tool_result(tool_result: ToolResult) -> None:
        """发布工具结果事件"""
        publish_event(create_tool_result_event(tool_result))

    @staticmethod
    def publish_thinking(thinking: str) -> None:
        """发布思考事件"""
        publish_event(create_thinking_event(thinking))

    @staticmethod
    def publish_turn_update(current_turn: int, max_turns: int) -> None:
        """发布轮次更新事件"""
        publish_event(create_turn_update_event(current_turn, max_turns))

    @staticmethod
    def publish_turn_complete(turns_used: int) -> None:
        """发布轮次完成事件"""
        publish_event(create_turn_complete_event(turns_used))

    @staticmethod
    def publish_session_update(session_state: SessionState) -> None:
        """发布会话更新事件"""
        publish_event(create_session_update_event(session_state))

    @staticmethod
    def publish_permission_request(tool_name: str, arguments: dict[str, Any]) -> None:
        """发布权限请求事件"""
        publish_event(create_permission_request_event(tool_name, arguments))

    @staticmethod
    def publish_permission_response(allowed: bool, reason: str = "",
                                   tool_name: str = "", arguments: dict[str, Any] | None = None) -> None:
        """发布权限响应事件"""
        from ..domain import PermissionDecision
        decision = PermissionDecision(
            allowed=allowed,
            reason=reason,
            tool_name=tool_name,
            arguments=arguments or {}
        )
        publish_event(create_permission_response_event(decision))

    @staticmethod
    def publish_status(data: dict[str, Any]) -> None:
        """发布状态事件"""
        publish_event(RuntimeEvent(type="status", data=data))

    @staticmethod
    def publish_error(data: dict[str, Any]) -> None:
        """发布错误事件"""
        publish_event(RuntimeEvent(type="error", data=data))


def create_base_event_handler() -> BaseEventHandler:
    """创建基础事件处理器"""
    return BaseEventHandler()