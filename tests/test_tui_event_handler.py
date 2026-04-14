"""测试 TUI 事件处理器（重构后）"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock
from rich.text import Text

from ggbot.core.domain import (
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
from ggbot.core.event_handlers.base_handler import BaseEventHandler
from ggbot.ui.renderers.tui_renderer import TuiRenderer


class MockTui:
    """模拟的 TUI 类"""

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


def test_base_event_handler_initialization():
    """测试基础事件处理器初始化"""
    handler = BaseEventHandler()

    # 验证处理器已创建
    assert hasattr(handler, 'state')
    assert hasattr(handler, '_subscriptions')
    assert handler.state.session_id == ""


def test_tui_renderer_assistant_delta():
    """测试TUI渲染器助手增量输出事件处理"""
    mock_tui = MockTui()
    renderer = TuiRenderer(mock_tui)

    # 发布助手增量输出事件
    from ggbot.core.event_bus import publish_event
    publish_event(create_assistant_delta_event("Hello "))

    # 给事件总线一些时间处理
    import time
    time.sleep(0.1)

    # 验证 TUI 被调用
    assert len(mock_tui._calls) > 0
    assert any("_stream_delta" in str(call) for call in mock_tui._calls)


def test_tui_event_handler_assistant_final():
    """测试助手最终输出事件处理"""
    mock_tui = MockTui()
    handler = TuiEventHandler(mock_tui)

    # 发布助手最终输出事件
    from ggbot.core.event_bus import publish_event
    publish_event(create_assistant_final_event("Final answer"))

    # 给事件总线一些时间处理
    import time
    time.sleep(0.1)

    # 验证 TUI 被调用
    assert len(mock_tui._calls) > 0
    assert any("_append_assistant_final" in str(call) for call in mock_tui._calls)


def test_tui_event_handler_thinking():
    """测试思考事件处理"""
    mock_tui = MockTui()
    mock_tui._thinking_enabled = True  # 启用思考功能
    handler = TuiEventHandler(mock_tui)

    # 发布思考事件
    from ggbot.core.event_bus import publish_event
    publish_event(create_thinking_event("I'm thinking about this..."))

    # 给事件总线一些时间处理
    import time
    time.sleep(0.1)

    # 验证日志被写入
    assert len(mock_tui._log_writes) > 0


def test_tui_event_handler_tool_call():
    """测试工具调用事件处理"""
    mock_tui = MockTui()
    handler = TuiEventHandler(mock_tui)

    # 创建工具调用事件
    tool_call = ToolCall(
        id="call_123",
        function=ToolFunction(name="test_tool", arguments='{"param": "value"}')
    )
    tool_call_event = create_tool_call_event(tool_call)

    # 发布工具调用事件
    from ggbot.core.event_bus import publish_event
    publish_event(tool_call_event)

    # 给事件总线一些时间处理
    import time
    time.sleep(0.1)

    # 验证日志被写入
    assert len(mock_tui._log_writes) > 0
    # 检查是否包含工具名
    log_contents = [str(write) for write in mock_tui._log_writes]
    assert any("test_tool" in content for content in log_contents)


def test_tui_event_handler_tool_result():
    """测试工具结果事件处理"""
    mock_tui = MockTui()
    handler = TuiEventHandler(mock_tui)

    # 创建工具结果事件
    tool_result = ToolResult(
        tool_call_id="call_123",
        name="test_tool",
        content="Tool executed successfully",
        error=False,
        auto_healed=False
    )
    tool_result_event = create_tool_result_event(tool_result)

    # 发布工具结果事件
    from ggbot.core.event_bus import publish_event
    publish_event(tool_result_event)

    # 给事件总线一些时间处理
    import time
    time.sleep(0.1)

    # 验证日志被写入
    assert len(mock_tui._log_writes) > 0


def test_tui_event_handler_status_update():
    """测试状态更新事件处理"""
    mock_tui = MockTui()
    handler = TuiEventHandler(mock_tui)

    # 发布状态事件（模拟 status_update 工具）
    from ggbot.core.event_bus import publish_event
    publish_event(RuntimeEvent(type="status", data={"message": "Processing..."}))

    # 给事件总线一些时间处理
    import time
    time.sleep(0.1)

    # 验证状态更新被处理
    assert len(mock_tui._status_updates) > 0
    assert mock_tui._render_status_calls > 0
    assert mock_tui._render_top_right_calls > 0


def test_tui_event_handler_turn_update():
    """测试轮次更新事件处理"""
    mock_tui = MockTui()
    handler = TuiEventHandler(mock_tui)

    # 发布轮次更新事件
    from ggbot.core.event_bus import publish_event
    publish_event(create_turn_update_event(2, 8))

    # 给事件总线一些时间处理
    import time
    time.sleep(0.1)

    # 验证 TUI 状态被更新
    assert mock_tui._render_status_calls > 0


def test_tui_event_handler_session_update():
    """测试会话更新事件处理"""
    mock_tui = MockTui()
    handler = TuiEventHandler(mock_tui)

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
    from ggbot.core.event_bus import publish_event
    publish_event(create_session_update_event(session_state))

    # 给事件总线一些时间处理
    import time
    time.sleep(0.1)

    # 验证状态被渲染
    assert mock_tui._render_status_calls > 0


def test_tui_event_handler_error():
    """测试错误事件处理"""
    mock_tui = MockTui()
    handler = TuiEventHandler(mock_tui)

    # 发布错误事件
    from ggbot.core.event_bus import publish_event
    publish_event(RuntimeEvent(type="error", data={"error": "Something went wrong"}))

    # 给事件总线一些时间处理
    import time
    time.sleep(0.1)

    # 验证错误被记录
    assert len(mock_tui._log_writes) > 0
    log_contents = [str(write) for write in mock_tui._log_writes]
    assert any("error" in content.lower() for content in log_contents)


def test_tui_event_handler_static_methods():
    """测试 TUI 事件处理器的静态发布方法"""
    # 测试助手增量输出发布
    TuiEventHandler.publish_assistant_delta("Hello")

    # 测试助手最终输出发布
    TuiEventHandler.publish_assistant_final("Hello World")

    # 测试工具调用发布
    tool_call = ToolCall(
        id="call_123",
        function=ToolFunction(name="test_tool", arguments='{"param": "value"}')
    )
    TuiEventHandler.publish_tool_call(tool_call)

    # 测试工具结果发布
    tool_result = ToolResult(
        tool_call_id="call_123",
        name="test_tool",
        content="Result",
        error=False,
        auto_healed=False
    )
    TuiEventHandler.publish_tool_result(tool_result)

    # 测试思考发布
    TuiEventHandler.publish_thinking("Thinking...")

    # 测试轮次更新发布
    TuiEventHandler.publish_turn_update(2, 8)

    # 测试轮次完成发布
    TuiEventHandler.publish_turn_complete(3)

    # 测试会话更新发布
    session_state = SessionState(
        session_id="test",
        title="Test",
        user_turns=1,
        current_turn=1,
        max_turns=8,
        thinking_enabled=False
    )
    TuiEventHandler.publish_session_update(session_state)

    # 测试权限请求发布
    TuiEventHandler.publish_permission_request("shell_run", {"command": "ls"})

    # 测试权限响应发布
    from ggbot.core.domain import PermissionDecision
    decision = PermissionDecision(allowed=True, reason="Approved", tool_name="shell_run")
    TuiEventHandler.publish_permission_response(decision)

    # 测试状态发布
    TuiEventHandler.publish_status({"message": "Processing"})

    # 测试错误发布
    TuiEventHandler.publish_error({"error": "Test error"})

    # 验证方法存在且可调用
    assert callable(TuiEventHandler.publish_assistant_delta)
    assert callable(TuiEventHandler.publish_assistant_final)
    assert callable(TuiEventHandler.publish_tool_call)
    assert callable(TuiEventHandler.publish_tool_result)
    assert callable(TuiEventHandler.publish_thinking)
    assert callable(TuiEventHandler.publish_turn_update)
    assert callable(TuiEventHandler.publish_turn_complete)
    assert callable(TuiEventHandler.publish_session_update)
    assert callable(TuiEventHandler.publish_permission_request)
    assert callable(TuiEventHandler.publish_permission_response)
    assert callable(TuiEventHandler.publish_status)
    assert callable(TuiEventHandler.publish_error)


def test_tui_event_handler_cleanup():
    """测试事件处理器清理"""
    mock_tui = MockTui()
    handler = TuiEventHandler(mock_tui)

    # 获取初始订阅数量
    from ggbot.core.event_bus import get_global_event_bus
    bus = get_global_event_bus()

    # 取消所有订阅
    handler.unsubscribe_all()

    # 发布事件，应该不会被处理
    from ggbot.core.event_bus import publish_event
    initial_log_writes = len(mock_tui._log_writes)
    publish_event(create_assistant_delta_event("Test"))

    # 给事件总线一些时间处理
    import time
    time.sleep(0.1)

    # 验证没有新日志写入
    assert len(mock_tui._log_writes) == initial_log_writes


if __name__ == "__main__":
    # 运行测试
    import pytest
    pytest.main([__file__, "-v"])