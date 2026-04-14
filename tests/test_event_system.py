"""测试事件系统和 transcript 记录器"""

import json
from pathlib import Path
import tempfile

from ggbot.core.domain import (
    RuntimeEvent,
    Message,
    ToolCall,
    ToolFunction,
    ToolResult,
    SessionState,
    PermissionDecision,
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
from ggbot.core.event_bus import EventBus, get_global_event_bus, publish_event
from ggbot.core.transcript import Transcript
from ggbot.core.transcript_logger import TranscriptLogger, create_transcript_logger


def test_event_bus_basic():
    """测试事件总线基本功能"""
    event_bus = EventBus()

    received_events = []

    def event_handler(event: RuntimeEvent):
        received_events.append(event)

    # 订阅所有事件
    subscription = event_bus.subscribe(event_handler)

    # 发布事件
    test_event = RuntimeEvent(type="test", data={"message": "hello"})
    event_bus.publish(test_event)

    assert len(received_events) == 1
    assert received_events[0].type == "test"
    assert received_events[0].data["message"] == "hello"

    # 取消订阅
    event_bus.unsubscribe(subscription)

    # 再次发布事件，应该不会被接收
    event_bus.publish(test_event)
    assert len(received_events) == 1  # 数量不变


def test_event_bus_selective_subscription():
    """测试选择性事件订阅"""
    event_bus = EventBus()

    received_type_a = []
    received_type_b = []

    def handler_a(event: RuntimeEvent):
        received_type_a.append(event)

    def handler_b(event: RuntimeEvent):
        received_type_b.append(event)

    # 订阅特定事件类型
    sub_a = event_bus.subscribe(handler_a, "type_a")
    sub_b = event_bus.subscribe(handler_b, ["type_b", "type_c"])

    # 发布事件
    event_a = RuntimeEvent(type="type_a", data={"id": 1})
    event_b = RuntimeEvent(type="type_b", data={"id": 2})
    event_c = RuntimeEvent(type="type_c", data={"id": 3})
    event_d = RuntimeEvent(type="type_d", data={"id": 4})

    event_bus.publish(event_a)
    event_bus.publish(event_b)
    event_bus.publish(event_c)
    event_bus.publish(event_d)

    assert len(received_type_a) == 1
    assert received_type_a[0].type == "type_a"

    assert len(received_type_b) == 2
    assert {e.type for e in received_type_b} == {"type_b", "type_c"}

    # 清理
    event_bus.unsubscribe(sub_a)
    event_bus.unsubscribe(sub_b)


def test_global_event_bus():
    """测试全局事件总线"""
    # 清除之前的全局事件总线
    global_bus = get_global_event_bus()
    global_bus.clear()

    received_events = []

    def event_handler(event: RuntimeEvent):
        received_events.append(event)

    # 使用全局函数订阅
    from ggbot.core.event_bus import subscribe_to_events
    subscription = subscribe_to_events(event_handler)

    # 使用全局函数发布
    test_event = RuntimeEvent(type="global_test", data={"value": 42})
    publish_event(test_event)

    assert len(received_events) == 1
    assert received_events[0].type == "global_test"
    assert received_events[0].data["value"] == 42

    # 清理
    global_bus.unsubscribe(subscription)


def test_domain_event_creation():
    """测试领域事件创建"""
    # 测试助手增量输出事件
    delta_event = create_assistant_delta_event("Hello")
    assert delta_event.type == "assistant_delta"
    assert delta_event.data["delta"] == "Hello"

    # 测试助手最终输出事件
    final_event = create_assistant_final_event("Hello World")
    assert final_event.type == "assistant_final"
    assert final_event.data["content"] == "Hello World"

    # 测试工具调用事件
    tool_call = ToolCall(
        id="call_123",
        function=ToolFunction(name="test_tool", arguments='{"param": "value"}')
    )
    tool_call_event = create_tool_call_event(tool_call)
    assert tool_call_event.type == "tool_call"
    assert tool_call_event.data["id"] == "call_123"

    # 测试工具结果事件
    tool_result = ToolResult(
        tool_call_id="call_123",
        name="test_tool",
        content="Result content",
        error=False,
        auto_healed=False
    )
    tool_result_event = create_tool_result_event(tool_result)
    assert tool_result_event.type == "tool_result"
    assert tool_result_event.data["name"] == "test_tool"

    # 测试思考事件
    thinking_event = create_thinking_event("I need to think about this")
    assert thinking_event.type == "thinking"
    assert thinking_event.data["thinking"] == "I need to think about this"

    # 测试轮次更新事件
    turn_update_event = create_turn_update_event(2, 8)
    assert turn_update_event.type == "turn_update"
    assert turn_update_event.data["current_turn"] == 2
    assert turn_update_event.data["max_turns"] == 8

    # 测试轮次完成事件
    turn_complete_event = create_turn_complete_event(3)
    assert turn_complete_event.type == "turn_complete"
    assert turn_complete_event.data["turns_used"] == 3

    # 测试会话更新事件
    session_state = SessionState(
        session_id="session_123",
        title="Test Session",
        user_turns=5,
        current_turn=2,
        max_turns=8,
        thinking_enabled=True
    )
    session_update_event = create_session_update_event(session_state)
    assert session_update_event.type == "session_update"
    assert session_update_event.data["session_id"] == "session_123"
    assert session_update_event.data["title"] == "Test Session"

    # 测试权限请求事件
    permission_request_event = create_permission_request_event(
        "shell_run",
        {"command": "ls -la"}
    )
    assert permission_request_event.type == "permission_request"
    assert permission_request_event.data["tool_name"] == "shell_run"

    # 测试权限响应事件
    decision = PermissionDecision(
        allowed=True,
        reason="User approved",
        tool_name="shell_run",
        arguments={"command": "ls -la"}
    )
    permission_response_event = create_permission_response_event(decision)
    assert permission_response_event.type == "permission_response"
    assert permission_response_event.data["allowed"] is True


def test_transcript_logger(tmp_path: Path):
    """测试 transcript 记录器"""
    transcript_path = tmp_path / "test_transcript.jsonl"
    transcript = Transcript(path=transcript_path)
    logger = create_transcript_logger(transcript)

    # 记录各种事件
    logger.log_domain_event(create_assistant_delta_event("Hello"))
    logger.log_domain_event(create_assistant_final_event("Hello World"))
    logger.log_domain_event(create_thinking_event("Thinking..."))

    # 验证 transcript 文件被创建
    assert transcript_path.exists()

    # 读取并验证内容
    with open(transcript_path, 'r', encoding='utf-8') as f:
        lines = [json.loads(line.strip()) for line in f if line.strip()]

    assert len(lines) >= 3  # 至少有三个事件

    # 验证事件类型
    event_types = {line["type"] for line in lines}
    assert "model_message" in event_types  # assistant_delta 和 assistant_final 应该被记录为 model_message
    assert "thinking" in event_types


def test_transcript_logger_event_subscription(tmp_path: Path):
    """测试 transcript 记录器的事件订阅"""
    transcript_path = tmp_path / "test_subscription.jsonl"
    transcript = Transcript(path=transcript_path)
    logger = create_transcript_logger(transcript)

    # 通过事件总线发布事件
    publish_event(create_assistant_delta_event("Test delta"))
    publish_event(create_thinking_event("Test thinking"))

    # 给事件总线一些时间处理
    import time
    time.sleep(0.1)

    # 验证 transcript 文件被创建并有内容
    assert transcript_path.exists()

    with open(transcript_path, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]

    assert len(lines) >= 2  # 至少有两个事件


def test_event_handler_class():
    """测试 EventHandler 基类"""
    from ggbot.core.event_bus import EventHandler

    class TestEventHandler(EventHandler):
        def __init__(self):
            super().__init__()
            self.received_events = []

            @self.subscribe(["test_event"])
            def on_test_event(event: RuntimeEvent):
                self.received_events.append(event)

    handler = TestEventHandler()

    # 发布事件
    test_event = RuntimeEvent(type="test_event", data={"test": "data"})
    publish_event(test_event)

    # 给事件总线一些时间处理
    import time
    time.sleep(0.1)

    assert len(handler.received_events) == 1
    assert handler.received_events[0].type == "test_event"

    # 清理
    handler.unsubscribe_all()


def test_message_conversion():
    """测试消息转换"""
    # 测试 Message 到字典的转换
    message = Message(
        role="user",
        content="Hello world",
        name=None,
        tool_call_id=None,
        tool_calls=None
    )

    message_dict = message.to_dict()
    assert message_dict["role"] == "user"
    assert message_dict["content"] == "Hello world"

    # 测试带工具调用的消息
    tool_call = ToolCall(
        id="call_123",
        function=ToolFunction(name="test_tool", arguments='{"param": "value"}')
    )

    message_with_tools = Message(
        role="assistant",
        content=None,
        name=None,
        tool_call_id=None,
        tool_calls=[tool_call]
    )

    message_with_tools_dict = message_with_tools.to_dict()
    assert message_with_tools_dict["role"] == "assistant"
    assert "tool_calls" in message_with_tools_dict
    assert len(message_with_tools_dict["tool_calls"]) == 1
    assert message_with_tools_dict["tool_calls"][0]["id"] == "call_123"


if __name__ == "__main__":
    # 运行测试
    import pytest
    pytest.main([__file__, "-v"])