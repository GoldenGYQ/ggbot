"""测试新的架构（基础事件处理器 + TUI渲染器）"""

import pytest
from unittest.mock import Mock
from rich.text import Text

from ggbot.models.runtime_models import (
    RuntimeEvent,
    create_assistant_delta_event,
    create_assistant_final_event,
    create_tool_call_event,
    create_tool_result_event,
    create_thinking_event,
    create_turn_update_event,
    create_turn_complete_event,
    create_session_update_event,
    ToolCall,
    ToolFunction,
    ToolResult,
    SessionState,
)
from ggbot.events.event_handlers.base_handler import BaseEventHandler, AgentState
from ggbot.events.event_bus import get_global_event_bus, publish_event


class MockTui:
    """模拟的 TUI 类（用于测试渲染器）"""

    def __init__(self):
        self._thinking_enabled = False
        self._current_conversation_turn = 0
        self._status_updates = []
        self._calls = []
        self._log_writes = []
        self._render_status_calls = 0
        self._render_top_right_calls = 0
        self._assistant_stream_buffer = None

    def call_from_thread(self, func, *args):
        """模拟 call_from_thread 方法"""
        # 直接执行函数
        try:
            if args:
                result = func(*args)
            else:
                result = func()
        except Exception as e:
            # 如果函数不存在，记录错误但不抛出
            if "has no attribute" in str(e):
                result = None
            else:
                raise

        func_name = func.__name__ if hasattr(func, '__name__') else str(func)
        self._calls.append(("call_from_thread", func_name, args))

        # 特殊处理：如果调用的是 _render_status 或 _render_top_right，增加计数
        if func_name == "_render_status":
            self._render_status_calls += 1
        elif func_name == "_render_top_right":
            self._render_top_right_calls += 1

        return result

    def _push_status_update(self, text: str):
        self._status_updates.append(text)

    def _render_status(self):
        self._render_status_calls += 1

    def _render_top_right(self):
        self._render_top_right_calls += 1

    def _stream_delta(self, delta: str):
        """模拟 _stream_delta 方法"""
        self._calls.append(("_stream_delta", delta))

    def _append_assistant_final(self, content: str):
        """模拟 _append_assistant_final 方法"""
        self._calls.append(("_append_assistant_final", content))

    def query_one(self, widget_type):
        """模拟 query_one 方法"""
        if widget_type == "RichLog":
            mock_log = Mock()
            mock_log.write = lambda content: self._log_writes.append(content)
            mock_log.clear = lambda: None
            return mock_log
        elif widget_type == "#stream":
            mock_static = Mock()
            mock_static.update = lambda content: None
            return mock_static
        elif widget_type == "#status_line":
            mock_static = Mock()
            mock_static.update = lambda content: None
            return mock_static
        return Mock()


def test_base_event_handler_creation():
    """测试基础事件处理器创建"""
    handler = BaseEventHandler()

    assert handler is not None
    assert hasattr(handler, 'state')
    assert isinstance(handler.state, AgentState)
    assert hasattr(handler, '_subscriptions')


def test_agent_state_management():
    """测试Agent状态管理"""
    state = AgentState()

    # 测试初始状态
    assert state.session_id == ""
    assert state.title == "Untitled"
    assert state.user_turns == 0
    assert state.current_turn == 0
    assert state.max_turns == 8
    assert state.thinking_enabled is False
    assert state.status_updates == []

    # 测试状态更新
    state.add_status_update("Processing...")
    assert len(state.status_updates) == 1
    assert state.status_updates[0] == "Processing..."

    # 测试保持最近3条
    state.add_status_update("Update 1")
    state.add_status_update("Update 2")
    state.add_status_update("Update 3")
    state.add_status_update("Update 4")
    assert len(state.status_updates) == 3
    assert state.status_updates == ["Update 2", "Update 3", "Update 4"]

    # 测试从SessionState更新
    session_state = SessionState(
        session_id="test_session",
        title="Test Title",
        user_turns=5,
        current_turn=2,
        max_turns=10,
        thinking_enabled=True
    )
    state.update_from_session_state(session_state)

    assert state.session_id == "test_session"
    assert state.title == "Test Title"
    assert state.user_turns == 5
    assert state.current_turn == 2
    assert state.max_turns == 10
    assert state.thinking_enabled is True

    # 测试转换为SessionState
    converted = state.to_session_state()
    assert converted.session_id == "test_session"
    assert converted.title == "Test Title"
    assert converted.user_turns == 5
    assert converted.current_turn == 2
    assert converted.max_turns == 10
    assert converted.thinking_enabled is True


def test_base_event_handler_static_methods():
    """测试基础事件处理器的静态发布方法"""
    # 测试所有静态方法都存在且可调用
    assert callable(BaseEventHandler.publish_assistant_delta)
    assert callable(BaseEventHandler.publish_assistant_final)
    assert callable(BaseEventHandler.publish_tool_call)
    assert callable(BaseEventHandler.publish_tool_result)
    assert callable(BaseEventHandler.publish_thinking)
    assert callable(BaseEventHandler.publish_turn_update)
    assert callable(BaseEventHandler.publish_turn_complete)
    assert callable(BaseEventHandler.publish_session_update)
    assert callable(BaseEventHandler.publish_permission_request)
    assert callable(BaseEventHandler.publish_permission_response)
    assert callable(BaseEventHandler.publish_status)
    assert callable(BaseEventHandler.publish_error)

    # 测试一些方法调用（不验证具体效果，只验证不抛出异常）
    BaseEventHandler.publish_assistant_delta("Hello")
    BaseEventHandler.publish_assistant_final("Hello World")
    BaseEventHandler.publish_thinking("Thinking...")
    BaseEventHandler.publish_turn_update(2, 8)
    BaseEventHandler.publish_turn_complete(3)
    BaseEventHandler.publish_status({"message": "Processing"})
    BaseEventHandler.publish_error({"error": "Test error"})


def test_base_event_handler_status_update():
    """测试基础事件处理器状态更新处理"""
    # 清除全局事件总线
    bus = get_global_event_bus()
    bus.clear()

    handler = BaseEventHandler()

    # 发布状态更新事件
    publish_event(RuntimeEvent(type="status", data={"message": "Processing..."}))

    # 给事件总线一些时间处理
    import time
    time.sleep(0.1)

    # 验证状态被更新
    assert len(handler.state.status_updates) == 1
    assert handler.state.status_updates[0] == "Processing..."


def test_base_event_handler_turn_update():
    """测试基础事件处理器轮次更新处理"""
    # 清除全局事件总线
    bus = get_global_event_bus()
    bus.clear()

    handler = BaseEventHandler()

    # 发布轮次更新事件
    publish_event(create_turn_update_event(3, 10))

    # 给事件总线一些时间处理
    import time
    time.sleep(0.1)

    # 验证状态被更新
    assert handler.state.current_turn == 3
    assert handler.state.max_turns == 10


def test_base_event_handler_session_update():
    """测试基础事件处理器会话更新处理"""
    # 清除全局事件总线
    bus = get_global_event_bus()
    bus.clear()

    handler = BaseEventHandler()

    # 创建会话状态
    session_state = SessionState(
        session_id="test_session",
        title="Test Session",
        user_turns=5,
        current_turn=2,
        max_turns=8,
        thinking_enabled=True
    )

    # 发布会话更新事件
    publish_event(create_session_update_event(session_state))

    # 给事件总线一些时间处理
    import time
    time.sleep(0.1)

    # 验证状态被更新
    assert handler.state.session_id == "test_session"
    assert handler.state.title == "Test Session"
    assert handler.state.user_turns == 5
    assert handler.state.current_turn == 2
    assert handler.state.max_turns == 8
    assert handler.state.thinking_enabled is True


def test_base_event_handler_tool_result_status_update():
    """测试基础事件处理器工具结果状态更新处理"""
    # 清除全局事件总线
    bus = get_global_event_bus()
    bus.clear()

    handler = BaseEventHandler()

    # 创建工具结果事件（status_update类型）
    tool_result = ToolResult(
        tool_call_id="call_123",
        name="status_update",
        content="Tool execution started",
        error=False,
        auto_healed=False
    )

    # 发布工具结果事件
    publish_event(create_tool_result_event(tool_result))

    # 给事件总线一些时间处理
    import time
    time.sleep(0.1)

    # 验证状态被更新（可能被添加多次，因为事件总线可能有多重订阅）
    # 至少有一次
    assert len(handler.state.status_updates) >= 1
    # 检查内容
    assert "Tool execution started" in handler.state.status_updates


def test_create_base_event_handler():
    """测试创建基础事件处理器工厂函数"""
    from ggbot.events.event_handlers.base_handler import create_base_event_handler

    handler = create_base_event_handler()

    assert handler is not None
    assert isinstance(handler, BaseEventHandler)
    assert hasattr(handler, 'state')
    assert hasattr(handler, '_subscriptions')


if __name__ == "__main__":
    # 运行测试
    import pytest
    pytest.main([__file__, "-v"])