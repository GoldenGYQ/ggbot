from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from rich.text import Text

from ...models.runtime_models import (
    PermissionDecision,
    RuntimeEvent,
    ToolCall,
    ToolFunction,
    ToolResult,
    create_assistant_delta_event,
    create_assistant_final_event,
    create_permission_request_event,
    create_permission_response_event,
    create_session_update_event,
    create_thinking_event,
    create_tool_call_event,
    create_tool_result_event,
    create_turn_complete_event,
    create_turn_update_event,
)
from ...events.event_bus import EventBus, EventHandler, publish_event
from ...models.runtime_models import ToolCall as CoreToolCall


@dataclass(frozen=True)
class TuiRenderHooks:
    on_assistant_delta: Callable[[str], None]
    on_assistant_final: Callable[[str], None]
    on_tool_call: Callable[[str], None]
    on_tool_result: Callable[[str, str, bool], None]
    on_thinking: Callable[[str], None]
    on_plan_update: Callable[[list[dict[str, Any]]], None]
    on_turn_update: Callable[[], None]
    on_turn_complete: Callable[[], None]
    on_session_update: Callable[[], None]
    on_error: Callable[[str], None]
    on_status: Callable[[str], None]
    on_permission_request: Callable[[str, dict[str, str]], None]
    on_debug_event: Callable[[str], None]
    is_debug_enabled: Callable[[], bool]


def create_tui_render_hooks(tui: Any) -> TuiRenderHooks:
    def _on_status(status_msg: str) -> None:
        tui.call_from_thread(tui._push_status_update, status_msg)
        tui.call_from_thread(tui._render_top_right)
        tui.call_from_thread(tui._render_status)
        tui.call_from_thread(tui._render_status_message, status_msg)

    return TuiRenderHooks(
        on_assistant_delta=lambda delta: tui.call_from_thread(tui._stream_delta, delta),
        on_assistant_final=lambda content: tui.call_from_thread(tui._append_assistant_final, content),
        on_tool_call=lambda name: tui.call_from_thread(tui._render_tool_call, name),
        on_tool_result=lambda name, content, error: tui.call_from_thread(
            tui._render_tool_result, name, content, error
        ),
        on_thinking=lambda thinking: tui.call_from_thread(tui._render_thinking, thinking),
        on_plan_update=lambda plan: tui.call_from_thread(tui._render_plan, plan),
        on_turn_update=lambda: tui.call_from_thread(tui._render_status),
        on_turn_complete=lambda: tui.call_from_thread(tui._render_status),
        on_session_update=lambda: tui.call_from_thread(tui._render_status),
        on_error=lambda error_msg: tui.call_from_thread(tui._render_error, error_msg),
        on_status=_on_status,
        on_permission_request=lambda tool_name, arguments: tui.call_from_thread(
            tui._handle_permission_request, tool_name, arguments
        ),
        on_debug_event=lambda event_type: tui.call_from_thread(tui._render_debug_event, event_type),
        is_debug_enabled=lambda: bool(getattr(tui, "_debug_events", False)),
    )


class TuiRenderer(EventHandler):
    """TUI渲染器（只做UI渲染，不处理业务逻辑）"""

    def __init__(self, hooks: TuiRenderHooks | Any, event_bus: EventBus | None = None):
        super().__init__(event_bus=event_bus)
        self.hooks = hooks
        self._setup_subscriptions()

    def _setup_subscriptions(self) -> None:
        """设置事件订阅（只订阅需要渲染的事件）"""

        # 订阅助手增量输出事件 - 只做渲染
        @self.subscribe(["assistant_delta"])
        def on_assistant_delta(event: RuntimeEvent) -> None:
            delta = event.data.get("delta", "")
            if delta:
                self.hooks.on_assistant_delta(delta)

        # 订阅助手最终输出事件 - 只做渲染
        @self.subscribe(["assistant_final"])
        def on_assistant_final(event: RuntimeEvent) -> None:
            content = event.data.get("content", "")
            if content:
                self.hooks.on_assistant_final(content)

        # 订阅工具调用事件 - 只做渲染
        @self.subscribe(["tool_call"])
        def on_tool_call(event: RuntimeEvent) -> None:
            tool_call_data = event.data
            name = tool_call_data.get("function", {}).get("name") or tool_call_data.get("name", "unknown")
            self.hooks.on_tool_call(str(name))

        # 订阅工具结果事件 - 只做渲染
        @self.subscribe(["tool_result"])
        def on_tool_result(event: RuntimeEvent) -> None:
            tool_result_data = event.data
            name = tool_result_data.get("name", "unknown")
            content = tool_result_data.get("content", "")
            error = tool_result_data.get("error", False)
            self.hooks.on_tool_result(str(name), str(content), bool(error))

        # 订阅思考事件 - 只做渲染
        @self.subscribe(["thinking"])
        def on_thinking(event: RuntimeEvent) -> None:
            thinking = event.data.get("thinking", "")
            if thinking:
                self.hooks.on_thinking(str(thinking))

        # 订阅计划更新事件 - 只做渲染
        @self.subscribe(["plan_update"])
        def on_plan_update(event: RuntimeEvent) -> None:
            plan = event.data.get("plan", [])
            if plan:
                self.hooks.on_plan_update(plan)

        # 订阅轮次更新事件 - 只做渲染
        @self.subscribe(["turn_update"])
        def on_turn_update(event: RuntimeEvent) -> None:
            self.hooks.on_turn_update()

        # 订阅轮次完成事件 - 只做渲染
        @self.subscribe(["turn_complete"])
        def on_turn_complete(event: RuntimeEvent) -> None:
            self.hooks.on_turn_complete()

        # 订阅会话更新事件 - 只做渲染
        @self.subscribe(["session_update"])
        def on_session_update(event: RuntimeEvent) -> None:
            self.hooks.on_session_update()

        # 订阅错误事件 - 只做渲染
        @self.subscribe(["error"])
        def on_error(event: RuntimeEvent) -> None:
            error_msg = event.data.get("error", "Unknown error")
            self.hooks.on_error(str(error_msg))

        # 订阅状态事件 - 只做渲染
        @self.subscribe(["status"])
        def on_status(event: RuntimeEvent) -> None:
            status_msg = event.data.get("message", "")
            if status_msg:
                self.hooks.on_status(str(status_msg))

        # 订阅权限请求事件 - 只做渲染
        @self.subscribe(["permission_request"])
        def on_permission_request(event: RuntimeEvent) -> None:
            tool_name = event.data.get("tool_name", "")
            arguments = event.data.get("arguments", {})
            normalized_arguments = arguments if isinstance(arguments, dict) else {}
            self.hooks.on_permission_request(str(tool_name), normalized_arguments)

        # 订阅所有事件（用于调试）- 只做渲染
        @self.subscribe(None)
        def on_all_events(event: RuntimeEvent) -> None:
            # 调试用：记录所有事件
            if self.hooks.is_debug_enabled():
                self.hooks.on_debug_event(str(event.type))


def create_tui_renderer(tui: Any, event_bus: EventBus | None = None) -> TuiRenderer:
    """创建TUI渲染器"""
    return TuiRenderer(create_tui_render_hooks(tui), event_bus=event_bus)


def _coerce_tool_call(tool_call: ToolCall | CoreToolCall | dict[str, Any]) -> ToolCall:
    if isinstance(tool_call, ToolCall):
        return tool_call

    if isinstance(tool_call, CoreToolCall):
        return ToolCall(
            id=tool_call.id,
            type=tool_call.type,
            function=ToolFunction(
                name=tool_call.function.name,
                arguments=tool_call.function.arguments,
            ),
        )

    if isinstance(tool_call, dict):
        fn_raw = tool_call.get("function")
        fn: dict[str, Any] = fn_raw if isinstance(fn_raw, dict) else {}
        fn_name = str(fn.get("name") or tool_call.get("name") or "unknown")
        fn_args = str(fn.get("arguments") or "")
        return ToolCall(
            id=str(tool_call.get("id") or ""),
            type=str(tool_call.get("type") or "function"),
            function=ToolFunction(name=fn_name, arguments=fn_args),
        )

    raise TypeError(f"Unsupported tool_call type: {type(tool_call).__name__}")


def _coerce_tool_result(tool_result: ToolResult | dict[str, Any]) -> ToolResult:
    if isinstance(tool_result, ToolResult):
        return tool_result

    if isinstance(tool_result, dict):
        return ToolResult(
            tool_call_id=str(tool_result.get("tool_call_id") or tool_result.get("id") or ""),
            name=str(tool_result.get("name") or "unknown"),
            content=str(tool_result.get("content") or ""),
            error=bool(tool_result.get("error", False)),
            auto_healed=bool(tool_result.get("auto_healed", False)),
        )

    raise TypeError(f"Unsupported tool_result type: {type(tool_result).__name__}")


def _publish_assistant_delta(delta: str) -> None:
    publish_event(create_assistant_delta_event(delta))


def _publish_assistant_final(content: str) -> None:
    publish_event(create_assistant_final_event(content))


def _publish_tool_call(tool_call: ToolCall | CoreToolCall | dict[str, Any]) -> None:
    publish_event(create_tool_call_event(_coerce_tool_call(tool_call)))


def _publish_tool_result(tool_result: ToolResult | dict[str, Any]) -> None:
    publish_event(create_tool_result_event(_coerce_tool_result(tool_result)))


def _publish_thinking(thinking: str) -> None:
    publish_event(create_thinking_event(thinking))


def _publish_turn_update(current_turn: int, max_turns: int) -> None:
    publish_event(create_turn_update_event(current_turn, max_turns))


def _publish_turn_complete(turns_used: int) -> None:
    publish_event(create_turn_complete_event(turns_used))


def _publish_session_update(session_state: Any) -> None:
    publish_event(create_session_update_event(session_state))


def _publish_permission_request(tool_name: str, arguments: dict[str, Any]) -> None:
    publish_event(create_permission_request_event(tool_name, arguments))


def _publish_permission_response(
    allowed: bool | PermissionDecision,
    reason: str = "",
    tool_name: str = "",
    arguments: dict[str, Any] | None = None,
) -> None:
    if isinstance(allowed, PermissionDecision):
        decision = allowed
    else:
        decision = PermissionDecision(
            allowed=allowed,
            reason=reason,
            tool_name=tool_name,
            arguments=arguments or {},
        )
    publish_event(create_permission_response_event(decision))


def _publish_status(data: dict[str, Any]) -> None:
    publish_event(RuntimeEvent(type="status", data=data))


def _publish_error(data: dict[str, Any]) -> None:
    publish_event(RuntimeEvent(type="error", data=data))


class TuiEventHandler(TuiRenderer):
    """Backward-compatible alias with static event publish helpers."""

    publish_assistant_delta = staticmethod(_publish_assistant_delta)
    publish_assistant_final = staticmethod(_publish_assistant_final)
    publish_tool_call = staticmethod(_publish_tool_call)
    publish_tool_result = staticmethod(_publish_tool_result)
    publish_thinking = staticmethod(_publish_thinking)
    publish_turn_update = staticmethod(_publish_turn_update)
    publish_turn_complete = staticmethod(_publish_turn_complete)
    publish_session_update = staticmethod(_publish_session_update)
    publish_permission_request = staticmethod(_publish_permission_request)
    publish_permission_response = staticmethod(_publish_permission_response)
    publish_status = staticmethod(_publish_status)
    publish_error = staticmethod(_publish_error)