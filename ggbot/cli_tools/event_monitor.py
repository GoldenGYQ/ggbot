"""事件监听器 - 实时监听运行时事件"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from typing import Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import threading
import queue

from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.text import Text
from rich.panel import Panel
from rich.columns import Columns
from rich.layout import Layout
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt

from ..domain.domain import RuntimeEvent, RuntimeEventType
from ..events.event_bus import subscribe_to_events, get_global_event_bus


class OutputFormat(str, Enum):
    """输出格式"""
    TEXT = "text"  # 纯文本
    JSON = "json"  # JSON格式
    RICH = "rich"  # Rich格式化
    TABLE = "table"  # 表格格式


@dataclass
class EventFilter:
    """事件过滤器"""
    event_types: Optional[list[RuntimeEventType]] = None
    source_pattern: Optional[str] = None
    data_pattern: Optional[str] = None
    min_severity: Optional[str] = None  # 用于status/error事件

    def matches(self, event: RuntimeEvent) -> bool:
        """检查事件是否匹配过滤器"""
        # 事件类型过滤
        if self.event_types and event.type not in self.event_types:
            return False

        # 来源过滤
        if self.source_pattern and self.source_pattern not in event.source:
            return False

        # 数据内容过滤
        if self.data_pattern:
            data_str = json.dumps(event.data, ensure_ascii=False)
            if self.data_pattern not in data_str:
                return False

        # 严重性过滤（仅适用于status/error事件）
        if self.min_severity and event.type in ["status", "error"]:
            severity = event.data.get("severity", "info")
            severity_levels = {"debug": 0, "info": 1, "warning": 2, "error": 3, "critical": 4}
            min_level = severity_levels.get(self.min_severity.lower(), 0)
            event_level = severity_levels.get(severity.lower(), 0)
            if event_level < min_level:
                return False

        return True


@dataclass
class EventStats:
    """事件统计"""
    total_events: int = 0
    events_by_type: dict[str, int] = field(default_factory=dict)
    events_by_source: dict[str, int] = field(default_factory=dict)
    last_event_time: float = 0
    events_per_second: float = 0.0

    def record_event(self, event: RuntimeEvent):
        """记录事件"""
        self.total_events += 1
        self.events_by_type[event.type] = self.events_by_type.get(event.type, 0) + 1
        self.events_by_source[event.source] = self.events_by_source.get(event.source, 0) + 1
        current_time = time.time()

        # 更新事件速率
        if self.last_event_time > 0:
            time_diff = current_time - self.last_event_time
            if time_diff > 0:
                self.events_per_second = 0.9 * self.events_per_second + 0.1 * (1.0 / time_diff)

        self.last_event_time = current_time

    def get_summary(self) -> dict[str, Any]:
        """获取统计摘要"""
        return {
            "total_events": self.total_events,
            "events_by_type": dict(self.events_by_type),
            "events_by_source": dict(self.events_by_source),
            "events_per_second": round(self.events_per_second, 2),
            "last_event_time": datetime.fromtimestamp(self.last_event_time).isoformat() if self.last_event_time > 0 else "Never"
        }


class EventFormatter:
    """事件格式化器"""

    def __init__(self, format_type: OutputFormat = OutputFormat.TEXT):
        self.format_type = format_type
        self.console = Console()

    def format_event(self, event: RuntimeEvent) -> str:
        """格式化事件为字符串"""
        if self.format_type == OutputFormat.JSON:
            return self._format_json(event)
        elif self.format_type == OutputFormat.RICH:
            return self._format_rich(event)
        elif self.format_type == OutputFormat.TABLE:
            return self._format_table(event)
        else:
            return self._format_text(event)

    def _format_text(self, event: RuntimeEvent) -> str:
        """纯文本格式"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        event_type = event.type
        source = event.source

        # 根据事件类型格式化数据
        if event.type == "assistant_delta":
            delta = event.data.get("delta", "")
            return f"[{timestamp}] {source} {event_type}: {delta}"
        elif event.type == "assistant_final":
            content = event.data.get("content", "")
            return f"[{timestamp}] {source} {event_type}: {content}"
        elif event.type == "tool_call":
            name = event.data.get("function", {}).get("name", "unknown")
            args = event.data.get("function", {}).get("arguments", {})
            return f"[{timestamp}] {source} {event_type}: {name}({args})"
        elif event.type == "tool_result":
            name = event.data.get("name", "unknown")
            error = event.data.get("error", False)
            status = "ERROR" if error else "OK"
            return f"[{timestamp}] {source} {event_type}: {name} -> {status}"
        elif event.type == "thinking":
            thinking = event.data.get("thinking", "")
            return f"[{timestamp}] {source} {event_type}: {thinking}"
        elif event.type == "status":
            message = event.data.get("message", "")
            severity = event.data.get("severity", "info")
            return f"[{timestamp}] {source} {event_type}({severity}): {message}"
        elif event.type == "error":
            error_msg = event.data.get("error", "Unknown error")
            return f"[{timestamp}] {source} {event_type}: {error_msg}"
        else:
            data_str = json.dumps(event.data, ensure_ascii=False, indent=2)
            return f"[{timestamp}] {source} {event_type}: {data_str}"

    def _format_json(self, event: RuntimeEvent) -> str:
        """JSON格式"""
        event_dict = {
            "timestamp": datetime.now().isoformat(),
            "type": event.type,
            "source": event.source,
            "data": event.data
        }
        return json.dumps(event_dict, ensure_ascii=False)

    def _format_rich(self, event: RuntimeEvent) -> str:
        """Rich格式化（返回可渲染对象）"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        # 根据事件类型选择颜色
        colors = {
            "assistant_delta": "cyan",
            "assistant_final": "green",
            "tool_call": "yellow",
            "tool_result": "blue",
            "thinking": "magenta",
            "status": "white",
            "error": "red",
            "turn_update": "cyan",
            "session_update": "green",
            "permission_request": "yellow",
            "permission_response": "blue"
        }

        color = colors.get(event.type, "white")

        # 创建格式化文本
        text = Text()
        text.append(f"[{timestamp}] ", style="dim")
        text.append(f"{event.source} ", style="bold")
        text.append(f"{event.type}", style=f"bold {color}")

        # 添加数据
        if event.data:
            data_str = json.dumps(event.data, ensure_ascii=False)
            if len(data_str) > 100:
                data_str = data_str[:100] + "..."
            text.append(f": {data_str}", style="dim")

        return text

    def _format_table(self, event: RuntimeEvent) -> str:
        """表格格式（返回可渲染对象）"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        table = Table(show_header=False, box=None)
        table.add_column("Field", style="bold")
        table.add_column("Value")

        table.add_row("Time", timestamp)
        table.add_row("Source", event.source)
        table.add_row("Type", event.type)

        # 添加数据字段
        if event.data:
            for key, value in event.data.items():
                if isinstance(value, (dict, list)):
                    value_str = json.dumps(value, ensure_ascii=False)
                    if len(value_str) > 50:
                        value_str = value_str[:50] + "..."
                else:
                    value_str = str(value)
                table.add_row(key, value_str)

        return table


class EventMonitor:
    """事件监视器"""

    def __init__(
        self,
        event_filter: Optional[EventFilter] = None,
        output_format: OutputFormat = OutputFormat.TEXT,
        max_queue_size: int = 1000
    ):
        self.event_filter = event_filter or EventFilter()
        self.formatter = EventFormatter(output_format)
        self.stats = EventStats()
        self.running = False
        self.event_queue = queue.Queue(maxsize=max_queue_size)
        self.subscription = None
        self.console = Console()

    def start(self):
        """启动事件监听"""
        if self.running:
            return

        self.running = True

        # 订阅事件
        def event_handler(event: RuntimeEvent):
            if self.event_filter.matches(event):
                try:
                    self.event_queue.put(event, timeout=0.1)
                except queue.Full:
                    # 队列满时丢弃最旧的事件
                    try:
                        self.event_queue.get_nowait()
                        self.event_queue.put(event, timeout=0.1)
                    except queue.Empty:
                        pass

        self.subscription = subscribe_to_events(event_handler)

        # 启动处理线程
        self.process_thread = threading.Thread(target=self._process_events, daemon=True)
        self.process_thread.start()

        self.console.print("[green]事件监听器已启动[/green]")

    def stop(self):
        """停止事件监听"""
        if not self.running:
            return

        self.running = False

        # 取消订阅
        if self.subscription:
            get_global_event_bus().unsubscribe(self.subscription)
            self.subscription = None

        # 等待处理线程结束
        if hasattr(self, 'process_thread'):
            self.process_thread.join(timeout=2.0)

        self.console.print("[yellow]事件监听器已停止[/yellow]")

    def _process_events(self):
        """处理事件队列"""
        while self.running:
            try:
                event = self.event_queue.get(timeout=0.5)
                if event is None:  # 停止信号
                    break

                # 更新统计
                self.stats.record_event(event)

                # 格式化并输出事件
                formatted = self.formatter.format_event(event)
                if isinstance(formatted, str):
                    self.console.print(formatted)
                else:
                    # Rich对象
                    self.console.print(formatted)

                self.event_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                self.console.print(f"[red]处理事件时出错: {e}[/red]")

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        return self.stats.get_summary()

    def print_stats(self):
        """打印统计信息"""
        stats = self.get_stats()
        self.console.print("\n[bold]事件统计:[/bold]")
        self.console.print(f"总事件数: {stats['total_events']}")
        self.console.print(f"事件速率: {stats['events_per_second']} events/sec")

        if stats['events_by_type']:
            self.console.print("\n按类型统计:")
            for event_type, count in stats['events_by_type'].items():
                self.console.print(f"  {event_type}: {count}")

        if stats['events_by_source']:
            self.console.print("\n按来源统计:")
            for source, count in stats['events_by_source'].items():
                self.console.print(f"  {source}: {count}")


def run_interactive_monitor(
    event_filter: Optional[EventFilter] = None,
    output_format: OutputFormat = OutputFormat.RICH
):
    """运行交互式事件监视器"""
    console = Console()

    # 创建布局
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main", ratio=2),
        Layout(name="stats", size=10),
        Layout(name="input", size=3)
    )

    # 创建监视器
    monitor = EventMonitor(event_filter, output_format)

    # 事件显示缓冲区
    event_buffer = []
    MAX_EVENTS = 50

    def update_display():
        """更新显示"""
        # 更新头部
        header_text = Text("🔍 GGbot 事件监视器", style="bold blue")
        header_text.append(" | 按 Ctrl+C 退出", style="dim")
        layout["header"].update(Panel(header_text, border_style="blue"))

        # 更新事件显示
        if event_buffer:
            events_text = Text()
            for event in event_buffer[-20:]:  # 显示最近20个事件
                formatter = EventFormatter(output_format)
                formatted = formatter.format_event(event)
                if isinstance(formatted, str):
                    events_text.append(formatted + "\n")
                else:
                    # 对于Rich对象，我们需要不同的处理方式
                    pass
            layout["main"].update(Panel(events_text, title="实时事件", border_style="green"))
        else:
            layout["main"].update(Panel("等待事件...", title="实时事件", border_style="dim"))

        # 更新统计信息
        stats = monitor.get_stats()
        stats_text = Text()
        stats_text.append(f"总事件数: {stats['total_events']}\n", style="bold")
        stats_text.append(f"事件速率: {stats['events_per_second']} events/sec\n")

        if stats['events_by_type']:
            stats_text.append("\n按类型:\n")
            for event_type, count in stats['events_by_type'].items():
                stats_text.append(f"  {event_type}: {count}\n")

        layout["stats"].update(Panel(stats_text, title="统计", border_style="yellow"))

        # 输入区域
        input_text = Text("输入命令: filter, stats, clear, help, quit", style="dim")
        layout["input"].update(Panel(input_text, border_style="dim"))

    # 事件处理回调
    def handle_event(event: RuntimeEvent):
        event_buffer.append(event)
        if len(event_buffer) > MAX_EVENTS:
            event_buffer.pop(0)
        update_display()

    # 启动监视器
    monitor.start()

    # 订阅事件
    subscription = subscribe_to_events(handle_event)

    try:
        with Live(layout, refresh_per_second=4, screen=True):
            update_display()

            # 命令处理循环
            while True:
                try:
                    command = Prompt.ask("命令", console=console)

                    if command == "quit" or command == "exit":
                        break
                    elif command == "stats":
                        monitor.print_stats()
                    elif command == "clear":
                        event_buffer.clear()
                        update_display()
                    elif command == "filter":
                        # TODO: 实现过滤器配置
                        console.print("过滤器配置功能待实现")
                    elif command == "help":
                        console.print("可用命令:")
                        console.print("  filter - 配置事件过滤器")
                        console.print("  stats  - 显示统计信息")
                        console.print("  clear  - 清除事件缓冲区")
                        console.print("  help   - 显示帮助")
                        console.print("  quit   - 退出")
                    else:
                        console.print(f"未知命令: {command}")

                    update_display()

                except KeyboardInterrupt:
                    break

    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
    finally:
        # 清理
        get_global_event_bus().unsubscribe(subscription)
        monitor.stop()


def run_simple_monitor(
    event_filter: Optional[EventFilter] = None,
    output_format: OutputFormat = OutputFormat.TEXT,
    duration: Optional[float] = None
):
    """运行简单的事件监视器"""
    console = Console()
    monitor = EventMonitor(event_filter, output_format)

    console.print("[green]开始监听事件...[/green]")
    console.print("按 Ctrl+C 停止\n")

    monitor.start()

    try:
        if duration:
            # 运行指定时长
            time.sleep(duration)
        else:
            # 持续运行直到中断
            while True:
                time.sleep(0.1)
    except KeyboardInterrupt:
        console.print("\n[yellow]停止监听...[/yellow]")
    finally:
        monitor.stop()
        monitor.print_stats()


def create_event_filter_from_args(
    event_types: Optional[list[str]] = None,
    source: Optional[str] = None,
    contains: Optional[str] = None,
    min_severity: Optional[str] = None
) -> EventFilter:
    """从命令行参数创建事件过滤器"""
    return EventFilter(
        event_types=event_types,
        source_pattern=source,
        data_pattern=contains,
        min_severity=min_severity
    )