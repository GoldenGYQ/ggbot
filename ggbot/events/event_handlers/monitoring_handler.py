"""监控事件处理器 - 用于监控和统计事件"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from datetime import datetime
import time

from ...domain.domain import RuntimeEvent
from ..event_bus import EventHandler, publish_event


@dataclass
class EventStats:
    """事件统计"""
    total_events: int = 0
    events_by_type: dict[str, int] = field(default_factory=dict)
    last_event_time: float = 0
    events_per_minute: float = 0.0
    error_count: int = 0
    tool_call_count: int = 0
    assistant_message_count: int = 0

    def record_event(self, event_type: str):
        """记录事件"""
        self.total_events += 1
        self.events_by_type[event_type] = self.events_by_type.get(event_type, 0) + 1
        self.last_event_time = time.time()

        # 更新特定类型计数
        if event_type == "error":
            self.error_count += 1
        elif event_type == "tool_call":
            self.tool_call_count += 1
        elif event_type in ["assistant_delta", "assistant_final"]:
            self.assistant_message_count += 1

    def get_summary(self) -> dict[str, Any]:
        """获取统计摘要"""
        current_time = time.time()
        time_diff = current_time - self.last_event_time if self.last_event_time > 0 else 0

        return {
            "total_events": self.total_events,
            "error_count": self.error_count,
            "tool_call_count": self.tool_call_count,
            "assistant_message_count": self.assistant_message_count,
            "last_event_time": datetime.fromtimestamp(self.last_event_time).isoformat() if self.last_event_time > 0 else "Never",
            "seconds_since_last_event": time_diff,
            "events_by_type": dict(self.events_by_type)
        }


class MonitoringHandler(EventHandler):
    """监控事件处理器 - 用于收集统计信息和监控"""

    def __init__(self, enable_alerts: bool = True):
        super().__init__()
        self.stats = EventStats()
        self._alerts_enabled = enable_alerts
        self._setup_subscriptions()

    def _setup_subscriptions(self):
        """设置监控订阅"""

        # 监控所有事件
        @self.subscribe(None)
        def monitor_all_events(event: RuntimeEvent):
            self.stats.record_event(event.type)

            # 根据事件类型进行特殊处理
            if event.type == "error" and self._alerts_enabled:
                self._alert_on_error(event)
            elif event.type == "tool_call" and self._alerts_enabled:
                self._alert_on_tool_call(event)
            elif event.type in ["assistant_delta", "assistant_final"]:
                self._track_assistant_message(event)

        # 监控高频率事件（警告）
        self._last_warning_time = 0

        @self.subscribe(None)
        def rate_monitor(event: RuntimeEvent):
            current_time = time.time()
            if self._last_warning_time > 0:
                time_diff = current_time - self._last_warning_time
                if time_diff < 0.1:  # 100ms内多次事件
                    self._warn_high_frequency(event.type, time_diff)

            self._last_warning_time = current_time

    def _alert_on_error(self, event: RuntimeEvent):
        """错误警报"""
        error_msg = event.data.get("error", "Unknown error")
        # 发布警报事件
        publish_event(RuntimeEvent(
            type="status",
            data={
                "message": f"错误警报: {error_msg[:50]}...",
                "severity": "error",
                "original_event": event.data
            }
        ))

    def _alert_on_tool_call(self, event: RuntimeEvent):
        """工具调用警报"""
        tool_name = event.data.get("function", {}).get("name", "unknown")
        # 发布工具调用通知
        publish_event(RuntimeEvent(
            type="status",
            data={
                "message": f"工具调用: {tool_name}",
                "severity": "info",
                "tool_name": tool_name
            }
        ))

    def _track_assistant_message(self, event: RuntimeEvent):
        """跟踪助手消息"""
        content = event.data.get("delta") or event.data.get("content") or ""
        if content:
            # 可以在这里进行消息分析
            pass

    def _warn_high_frequency(self, event_type: str, time_diff: float):
        """高频事件警告"""
        if time_diff < 0.05:  # 50ms内
            publish_event(RuntimeEvent(
                type="status",
                data={
                    "message": f"警告: {event_type} 事件频率过高 ({1/time_diff:.1f} events/sec)",
                    "severity": "warning"
                }
            ))

    def get_stats(self) -> dict[str, Any]:
        """获取当前统计信息"""
        return self.stats.get_summary()

    def reset_stats(self):
        """重置统计信息"""
        self.stats = EventStats()

    def set_alerts_enabled(self, enabled: bool):
        """启用/禁用警报"""
        self._alerts_enabled = enabled

    def get_event_rate(self, window_seconds: int = 60) -> float:
        """获取事件速率（事件/分钟）"""
        # 简单实现：基于总事件数和运行时间
        if self.stats.total_events == 0:
            return 0.0

        # 假设从第一个事件开始计时
        if self.stats.last_event_time == 0:
            return 0.0

        # 计算平均速率
        first_event_time = getattr(self, '_first_event_time', self.stats.last_event_time)
        if not hasattr(self, '_first_event_time'):
            self._first_event_time = first_event_time

        time_span = self.stats.last_event_time - self._first_event_time
        if time_span <= 0:
            return 0.0

        return (self.stats.total_events / time_span) * 60.0  # 转换为事件/分钟


def create_monitoring_handler(enable_alerts: bool = True) -> MonitoringHandler:
    """创建监控处理器"""
    return MonitoringHandler(enable_alerts=enable_alerts)


# 使用示例
if __name__ == "__main__":
    # 创建监控器
    monitor = create_monitoring_handler(enable_alerts=True)

    # 模拟一些事件
    from ...domain.domain import create_assistant_delta_event, create_tool_call_event
    from ..event_bus import publish_event
    from ...domain.domain import ToolCall, ToolFunction

    # 发布测试事件
    publish_event(create_assistant_delta_event("Hello"))

    tool_call = ToolCall(
        id="test_1",
        function=ToolFunction(name="test_tool", arguments='{"param": "value"}')
    )
    publish_event(create_tool_call_event(tool_call))

    publish_event(RuntimeEvent(type="error", data={"error": "Test error"}))

    # 等待事件处理
    import time
    time.sleep(0.1)

    # 获取统计信息
    stats = monitor.get_stats()
    print("事件统计:")
    for key, value in stats.items():
        print(f"  {key}: {value}")

    # 清理
    monitor.unsubscribe_all()