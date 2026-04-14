"""事件监听示例"""

import time
from ggbot.core.domain import (
    RuntimeEvent,
    create_assistant_delta_event,
    create_assistant_final_event,
    create_tool_call_event,
    create_tool_result_event,
    create_thinking_event,
    create_turn_update_event,
    create_session_update_event,
    ToolCall,
    ToolFunction,
    ToolResult,
    SessionState,
)
from ggbot.core.event_bus import subscribe_to_events, publish_event


def simple_event_listener():
    """简单事件监听器"""
    print("=== 简单事件监听器 ===")

    def on_event(event: RuntimeEvent):
        print(f"[事件] 类型: {event.type}, 数据: {event.data}")

    # 订阅所有事件
    subscription = subscribe_to_events(on_event)

    # 发布一些测试事件
    publish_event(create_assistant_delta_event("Hello "))
    publish_event(create_assistant_final_event("Hello World!"))
    publish_event(create_thinking_event("I'm thinking..."))

    # 给事件总线时间处理
    time.sleep(0.1)

    # 取消订阅
    subscription.callback = None  # 断开引用
    print("监听器已取消订阅\n")


def selective_event_listener():
    """选择性事件监听器"""
    print("=== 选择性事件监听器 ===")

    assistant_messages = []
    tool_calls = []

    def on_assistant(event: RuntimeEvent):
        if event.type == "assistant_delta":
            assistant_messages.append(f"增量: {event.data.get('delta')}")
        elif event.type == "assistant_final":
            assistant_messages.append(f"最终: {event.data.get('content')}")

    def on_tool(event: RuntimeEvent):
        if event.type == "tool_call":
            name = event.data.get("function", {}).get("name", "unknown")
            tool_calls.append(f"调用: {name}")
        elif event.type == "tool_result":
            name = event.data.get("name", "unknown")
            tool_calls.append(f"结果: {name}")

    # 只订阅助手相关事件
    sub1 = subscribe_to_events(on_assistant, ["assistant_delta", "assistant_final"])

    # 只订阅工具相关事件
    sub2 = subscribe_to_events(on_tool, ["tool_call", "tool_result"])

    # 发布测试事件
    tool_call = ToolCall(
        id="call_123",
        function=ToolFunction(name="test_tool", arguments='{"param": "value"}')
    )
    tool_result = ToolResult(
        tool_call_id="call_123",
        name="test_tool",
        content="Success",
        error=False,
        auto_healed=False
    )

    publish_event(create_tool_call_event(tool_call))
    publish_event(create_assistant_delta_event("Processing..."))
    publish_event(create_tool_result_event(tool_result))
    publish_event(create_assistant_final_event("Done!"))

    time.sleep(0.1)

    print(f"助手消息: {assistant_messages}")
    print(f"工具调用: {tool_calls}")

    # 清理
    sub1.callback = None
    sub2.callback = None
    print("监听器已清理\n")


def state_tracking_listener():
    """状态跟踪监听器"""
    print("=== 状态跟踪监听器 ===")

    class StateTracker:
        def __init__(self):
            self.current_turn = 0
            self.max_turns = 8
            self.session_title = "Untitled"
            self.status_updates = []

        def on_turn_update(self, event: RuntimeEvent):
            self.current_turn = event.data.get("current_turn", 0)
            self.max_turns = event.data.get("max_turns", 8)
            print(f"轮次更新: {self.current_turn}/{self.max_turns}")

        def on_session_update(self, event: RuntimeEvent):
            self.session_title = event.data.get("title", "Untitled")
            print(f"会话更新: {self.session_title}")

        def on_status(self, event: RuntimeEvent):
            status = event.data.get("message", "")
            if status:
                self.status_updates.append(status)
                # 保持最近5条
                if len(self.status_updates) > 5:
                    self.status_updates = self.status_updates[-5:]
                print(f"状态更新: {status}")

    tracker = StateTracker()

    # 订阅特定事件
    sub1 = subscribe_to_events(tracker.on_turn_update, "turn_update")
    sub2 = subscribe_to_events(tracker.on_session_update, "session_update")
    sub3 = subscribe_to_events(tracker.on_status, "status")

    # 发布测试事件
    publish_event(create_turn_update_event(2, 10))

    session_state = SessionState(
        session_id="test_123",
        title="测试会话",
        user_turns=5,
        current_turn=2,
        max_turns=10,
        thinking_enabled=True
    )
    publish_event(create_session_update_event(session_state))

    publish_event(RuntimeEvent(type="status", data={"message": "开始处理..."}))
    publish_event(RuntimeEvent(type="status", data={"message": "处理中..."}))
    publish_event(RuntimeEvent(type="status", data={"message": "完成！"}))

    time.sleep(0.1)

    print(f"最终状态: 轮次={tracker.current_turn}, 标题={tracker.session_title}")
    print(f"状态历史: {tracker.status_updates}")

    # 清理
    sub1.callback = None
    sub2.callback = None
    sub3.callback = None
    print("跟踪器已清理\n")


def event_handler_class_example():
    """使用EventHandler类的示例"""
    print("=== 使用EventHandler类 ===")

    from ggbot.core.event_bus import EventHandler

    class MyEventHandler(EventHandler):
        def __init__(self):
            super().__init__()
            self.event_count = 0

            # 使用装饰器订阅事件
            @self.subscribe(["assistant_delta", "assistant_final"])
            def on_assistant(event: RuntimeEvent):
                self.event_count += 1
                print(f"[助手事件 #{self.event_count}] {event.type}: {event.data.get('delta') or event.data.get('content')}")

            @self.subscribe(["thinking"])
            def on_thinking(event: RuntimeEvent):
                print(f"[思考] {event.data.get('thinking')}")

    handler = MyEventHandler()

    # 发布事件
    publish_event(create_assistant_delta_event("Hello "))
    publish_event(create_thinking_event("Let me think..."))
    publish_event(create_assistant_final_event("Hello World!"))

    time.sleep(0.1)

    print(f"总共处理了 {handler.event_count} 个助手事件")

    # 自动清理（EventHandler基类会在销毁时取消订阅）
    handler.unsubscribe_all()
    print("处理器已清理\n")


def real_time_monitoring():
    """实时监控示例"""
    print("=== 实时监控 ===")

    import threading
    import queue

    event_queue = queue.Queue()

    def event_monitor():
        """事件监控线程"""
        print("事件监控启动...")
        try:
            while True:
                try:
                    event = event_queue.get(timeout=1.0)
                    if event is None:  # 停止信号
                        break

                    # 处理事件
                    print(f"[监控] {event.type}: {str(event.data)[:50]}...")

                    # 特定事件类型的特殊处理
                    if event.type == "error":
                        print(f"  ⚠️  错误: {event.data.get('error')}")
                    elif event.type == "tool_call":
                        name = event.data.get("function", {}).get("name", "unknown")
                        print(f"  🛠️  工具调用: {name}")

                except queue.Empty:
                    continue
        except KeyboardInterrupt:
            pass
        print("事件监控停止")

    def event_collector(event: RuntimeEvent):
        """事件收集器（运行在主线程）"""
        event_queue.put(event)

    # 订阅所有事件
    subscription = subscribe_to_events(event_collector)

    # 启动监控线程
    monitor_thread = threading.Thread(target=event_monitor, daemon=True)
    monitor_thread.start()

    # 发布一些事件
    print("发布测试事件...")
    for i in range(3):
        publish_event(create_assistant_delta_event(f"Message part {i+1} "))
        time.sleep(0.1)

    publish_event(create_assistant_final_event("Complete message"))
    publish_event(RuntimeEvent(type="error", data={"error": "Test error"}))

    # 等待事件处理
    time.sleep(0.5)

    # 发送停止信号
    event_queue.put(None)
    monitor_thread.join(timeout=2.0)

    # 清理
    subscription.callback = None
    print("监控已停止\n")


def main():
    """运行所有示例"""
    print("=" * 60)
    print("事件监听示例")
    print("=" * 60)

    # 注意：需要先清理全局事件总线，避免之前的订阅影响
    from ggbot.core.event_bus import get_global_event_bus
    get_global_event_bus().clear()

    simple_event_listener()
    selective_event_listener()
    state_tracking_listener()
    event_handler_class_example()
    real_time_monitoring()

    print("所有示例完成！")


if __name__ == "__main__":
    main()