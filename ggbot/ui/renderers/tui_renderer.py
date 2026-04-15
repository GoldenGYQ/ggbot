from __future__ import annotations

from typing import TYPE_CHECKING, Any
from rich.text import Text

from ...core.domain import RuntimeEvent
from ...core.event_bus import EventBus, EventHandler
from ...core.event_handlers.base_handler import BaseEventHandler

if TYPE_CHECKING:
    from ..tui import GGbotTui


class TuiRenderer(EventHandler):
    """TUI渲染器（只做UI渲染，不处理业务逻辑）"""

    def __init__(self, tui: GGbotTui, event_bus: EventBus | None = None):
        super().__init__(event_bus=event_bus)
        self.tui = tui
        self._setup_subscriptions()

    def _setup_subscriptions(self) -> None:
        """设置事件订阅（只订阅需要渲染的事件）"""

        # 订阅助手增量输出事件 - 只做渲染
        @self.subscribe(["assistant_delta"])
        def on_assistant_delta(event: RuntimeEvent) -> None:
            delta = event.data.get("delta", "")
            if delta:
                self.tui.call_from_thread(self.tui._stream_delta, delta)

        # 订阅助手最终输出事件 - 只做渲染
        @self.subscribe(["assistant_final"])
        def on_assistant_final(event: RuntimeEvent) -> None:
            content = event.data.get("content", "")
            if content:
                self.tui.call_from_thread(self.tui._append_assistant_final, content)

        # 订阅工具调用事件 - 只做渲染
        @self.subscribe(["tool_call"])
        def on_tool_call(event: RuntimeEvent) -> None:
            tool_call_data = event.data
            name = tool_call_data.get("function", {}).get("name") or tool_call_data.get("name", "unknown")

            def write_tool_call():
                self.tui.query_one("RichLog").write(Text(f"[tool:{name}]", style="bold magenta"))

            self.tui.call_from_thread(write_tool_call)

        # 订阅工具结果事件 - 只做渲染
        @self.subscribe(["tool_result"])
        def on_tool_result(event: RuntimeEvent) -> None:
            tool_result_data = event.data
            name = tool_result_data.get("name", "unknown")
            content = tool_result_data.get("content", "")
            error = tool_result_data.get("error", False)

            def write_tool_result():
                if name == "status_update":
                    # status_update 已经在状态事件中处理
                    return

                if content:
                    self.tui.query_one("RichLog").write(content)
                self.tui.query_one("RichLog").write(Text(f"[/tool:{name}]", style="dim"))

                if error:
                    self.tui.query_one("RichLog").write(Text(f"Error in tool {name}", style="bold red"))

            self.tui.call_from_thread(write_tool_result)

        # 订阅思考事件 - 只做渲染
        @self.subscribe(["thinking"])
        def on_thinking(event: RuntimeEvent) -> None:
            thinking = event.data.get("thinking", "")
            if thinking and self.tui._thinking_enabled:
                def write_thinking():
                    self.tui.query_one("RichLog").write(Text(f"[thinking] {thinking}", style="dim yellow"))
                self.tui.call_from_thread(write_thinking)

        # 订阅轮次更新事件 - 只做渲染
        @self.subscribe(["turn_update"])
        def on_turn_update(event: RuntimeEvent) -> None:
            self.tui.call_from_thread(self.tui._render_status)

        # 订阅轮次完成事件 - 只做渲染
        @self.subscribe(["turn_complete"])
        def on_turn_complete(event: RuntimeEvent) -> None:
            self.tui.call_from_thread(self.tui._render_status)

        # 订阅会话更新事件 - 只做渲染
        @self.subscribe(["session_update"])
        def on_session_update(event: RuntimeEvent) -> None:
            self.tui.call_from_thread(self.tui._render_status)

        # 订阅错误事件 - 只做渲染
        @self.subscribe(["error"])
        def on_error(event: RuntimeEvent) -> None:
            error_msg = event.data.get("error", "Unknown error")
            def write_error():
                self.tui.query_one("RichLog").write(Text(f"[error] {error_msg}", style="bold red"))
            self.tui.call_from_thread(write_error)

        # 订阅状态事件 - 只做渲染
        @self.subscribe(["status"])
        def on_status(event: RuntimeEvent) -> None:
            status_msg = event.data.get("message", "")
            if status_msg:
                # 更新状态显示
                self.tui.call_from_thread(self.tui._push_status_update, status_msg)
                self.tui.call_from_thread(self.tui._render_top_right)
                self.tui.call_from_thread(self.tui._render_status)

                # 在日志中显示状态
                def write_status():
                    line = Text("[status] ", style="bold cyan")
                    line.append(status_msg)
                    self.tui.query_one("RichLog").write(line)
                self.tui.call_from_thread(write_status)

        # 订阅权限请求事件 - 只做渲染
        @self.subscribe(["permission_request"])
        def on_permission_request(event: RuntimeEvent) -> None:
            tool_name = event.data.get("tool_name", "")
            arguments = event.data.get("arguments", {})

            if tool_name == "shell_run":
                command = arguments.get("command", "")
                if command:
                    # 触发TUI的权限确认流程
                    def request_permission():
                        self.tui.confirm_shell_run(command)
                    self.tui.call_from_thread(request_permission)

        # 订阅所有事件（用于调试）- 只做渲染
        @self.subscribe(None)
        def on_all_events(event: RuntimeEvent) -> None:
            # 调试用：记录所有事件
            if hasattr(self.tui, "_debug_events") and self.tui._debug_events:
                def log_event():
                    self.tui.query_one("RichLog").write(Text(f"[event:{event.type}]", style="dim"))
                self.tui.call_from_thread(log_event)


def create_tui_renderer(tui: GGbotTui, event_bus: EventBus | None = None) -> TuiRenderer:
    """创建TUI渲染器"""
    return TuiRenderer(tui, event_bus=event_bus)


class TuiEventHandler(TuiRenderer):
    """Backward-compatible alias with static event publish helpers."""

    publish_assistant_delta = staticmethod(BaseEventHandler.publish_assistant_delta)
    publish_assistant_final = staticmethod(BaseEventHandler.publish_assistant_final)
    publish_tool_call = staticmethod(BaseEventHandler.publish_tool_call)
    publish_tool_result = staticmethod(BaseEventHandler.publish_tool_result)
    publish_thinking = staticmethod(BaseEventHandler.publish_thinking)
    publish_turn_update = staticmethod(BaseEventHandler.publish_turn_update)
    publish_turn_complete = staticmethod(BaseEventHandler.publish_turn_complete)
    publish_session_update = staticmethod(BaseEventHandler.publish_session_update)
    publish_permission_request = staticmethod(BaseEventHandler.publish_permission_request)
    publish_permission_response = staticmethod(BaseEventHandler.publish_permission_response)
    publish_status = staticmethod(BaseEventHandler.publish_status)
    publish_error = staticmethod(BaseEventHandler.publish_error)