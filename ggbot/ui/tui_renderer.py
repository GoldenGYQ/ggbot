from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..models.runtime_models import RuntimeEvent


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


class TuiRenderer:
    """RuntimeEvent -> UI hooks 渲染器，不依赖 event_bus。"""

    def __init__(self, hooks: TuiRenderHooks | Any):
        self.hooks = hooks if isinstance(hooks, TuiRenderHooks) else create_tui_render_hooks(hooks)

    def handle_event(self, event: RuntimeEvent) -> None:
        event_type = str(event.type)
        data = event.data

        if event_type == "assistant_delta":
            delta = str(data.get("delta", ""))
            if delta:
                self.hooks.on_assistant_delta(delta)
        elif event_type == "assistant_final":
            content = str(data.get("content", ""))
            if content:
                self.hooks.on_assistant_final(content)
        elif event_type == "tool_call":
            tool_call_data = data
            fn = tool_call_data.get("function")
            fn_map = fn if isinstance(fn, dict) else {}
            name = fn_map.get("name") or tool_call_data.get("name") or "unknown"
            self.hooks.on_tool_call(str(name))
        elif event_type == "tool_result":
            self.hooks.on_tool_result(
                str(data.get("name", "unknown")),
                str(data.get("content", "")),
                bool(data.get("error", False)),
            )
        elif event_type == "thinking":
            thinking = str(data.get("thinking", ""))
            if thinking:
                self.hooks.on_thinking(thinking)
        elif event_type == "plan_update":
            plan = data.get("plan", [])
            if isinstance(plan, list) and plan:
                self.hooks.on_plan_update(plan)
        elif event_type == "turn_update":
            self.hooks.on_turn_update()
        elif event_type == "turn_complete":
            self.hooks.on_turn_complete()
        elif event_type == "session_update":
            self.hooks.on_session_update()
        elif event_type == "error":
            self.hooks.on_error(str(data.get("error", "Unknown error")))
        elif event_type == "status":
            status_msg = str(data.get("message", ""))
            if status_msg:
                self.hooks.on_status(status_msg)
        elif event_type == "permission_request":
            tool_name = str(data.get("tool_name", ""))
            arguments_raw = data.get("arguments", {})
            arguments = arguments_raw if isinstance(arguments_raw, dict) else {}
            self.hooks.on_permission_request(tool_name, arguments)

        if self.hooks.is_debug_enabled():
            self.hooks.on_debug_event(event_type)


def create_tui_renderer(tui: Any) -> TuiRenderer:
    return TuiRenderer(create_tui_render_hooks(tui))
