from __future__ import annotations

import json
import time
import tracemalloc
import uuid
from pathlib import Path
from threading import Event
from collections.abc import Callable
from typing import cast

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Footer, Header, Input, RichLog, Static

from ggbot.state.sessions import default_sessions
from ggbot.runtime.agent_loop import run_query
from ggbot.runtime.agent_loop import ToolLimits
from ggbot.app.app_bootstrap import (
    AgentRuntime,
    create_agent_bootstrap,
    create_app_session,
    ensure_message_bootstrap,
    reset_runtime_history,
    switch_runtime_session,
)
from ggbot.events.runtime_events import consume_runtime_events
from ggbot.state.session_store import SessionStore
from ggbot.models.protocol_models import ChatMessage
from ggbot.models.runtime_models import RuntimeEvent, RuntimeEventType, SessionState, PermissionDecision
from ggbot.events.event_bus import EventBus
from ggbot.events.event_handlers.base_handler import BaseEventHandler, create_base_event_handler
from ggbot.tools.context import ToolContext
from .pets import PetBones, Species, list_species, render_sprite
from ggbot.ui.renderers.tui_renderer import TuiEventHandler, create_tui_renderer


def _new_session_id() -> str:
    return uuid.uuid4().hex

_GYQ666_LOGO_LINES = [
    " █████  █     █   █████     █████   █████   █████ ",
    "█        █   █   █     █   █       █       █      ",
    "█   ███   ███    █     █   ██████  ██████  ██████ ",
    "█     █    █     █     █   █     █ █     █ █     █",
    " █████     █      ███████   █████   █████   █████ ",
]


def _boxed_logo(lines: list[str], *, marker: str = "▼", pad: int = 2) -> str:
    if not lines:
        return ""

    content_width = max(len(s) for s in lines)
    inner_width = content_width + pad * 2

    # Top border with a center marker, similar to the example style.
    left = inner_width // 2
    right = inner_width - left - 1
    top = "╔" + ("═" * left) + marker + ("═" * right) + "╗"
    bottom = "╚" + ("═" * inner_width) + "╝"

    boxed: list[str] = [top]
    boxed.append("║" + (" " * inner_width) + "║")
    for s in lines:
        boxed.append("║" + (" " * pad) + s.center(content_width) + (" " * pad) + "║")
    boxed.append("║" + (" " * inner_width) + "║")
    boxed.append(bottom)
    return "\n".join(boxed)


def _format_pet_block(bones: PetBones) -> str:
    lines = render_sprite(bones, frame=0)
    return "\n".join(lines)

WELCOME_RIGHT = """Tips for getting started

- /clear to clear current session history
- /clear-screen to clear visible screen only
- /help for commands
- /exit to quit
"""


class GGbotTui(App[None]):
    CSS = """
    #top {
        height: auto;
    }

    #top_left, #top_right {
        width: 1fr;
        height: auto;
        padding: 1 2;
    }

    #log {
        height: 1fr;
        padding: 0 1;
    }

    #stream {
        height: auto;
        padding: 0 1;
    }

    #input {
        height: 7;
        padding: 0 1;
    }
    """

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+c", "copy_input", "Copy"),
        ("ctrl+v", "paste_input", "Paste"),
        ("ctrl+l", "clear_screen", "Clear Screen"),
        ("ctrl+up", "scroll_log_up", "Scroll Up"),
        ("ctrl+down", "scroll_log_down", "Scroll Down"),
    ]

    def __init__(self, runtime: AgentRuntime) -> None:
        super().__init__()
        self.runtime = runtime
        self._assistant_stream_buffer: str | None = None
        self._pet: PetBones = PetBones(species='duck')
        self._pending_shell_confirm: tuple[str, Event, dict[str, str | None]] | None = None
        self._pending_clear_confirm: bool = False
        self._busy: bool = False
        self._status_updates: list[str] = []
        self._session_store = SessionStore.load(self.runtime.settings.resolved_transcript_dir())
        self._session_store.ensure_saved(self.runtime.session_id)
        # Thinking functionality
        self._thinking_enabled: bool = self.runtime.settings.thinking_enabled
        # Current conversation turn tracking
        self._current_conversation_turn: int = 0
        self._resource_status: str = "CPU:0.0s MEM:0.0MB"
        self._event_bus = EventBus()
        # Event handling with new architecture
        self._event_handler = create_base_event_handler(event_bus=self._event_bus)  # 业务逻辑处理器
        self._tui_renderer = create_tui_renderer(self, event_bus=self._event_bus)     # UI渲染器
        self._debug_events: bool = False  # 设置为 True 可以调试事件流
        # Permission prompt tracking
        self._showing_permission_prompt: bool = False

        # 自定义事件监听器（示例）
        self._custom_listeners: list = []
        self._setup_custom_event_listeners()

    def _setup_custom_event_listeners(self):
        """设置自定义事件监听器（示例）"""
        # 示例1：监听所有事件并记录（调试用）
        if self._debug_events:
            def debug_listener(event: RuntimeEvent):
                def log():
                    self.query_one(RichLog).write(f"[debug:{event.type}]")
                self.call_from_thread(log)

            sub = self._event_bus.subscribe(debug_listener)
            self._custom_listeners.append(sub)

        # 示例2：监听工具调用并统计
        tool_call_count = 0

        def tool_call_listener(event: RuntimeEvent):
            nonlocal tool_call_count
            if event.type == "tool_call":
                tool_call_count += 1
                def update_status():
                    # 在状态栏显示工具调用计数
                    self._push_status_update(f"工具调用: {tool_call_count}")
                    self._render_top_right()
                self.call_from_thread(update_status)

        sub = self._event_bus.subscribe(tool_call_listener, "tool_call")
        self._custom_listeners.append(sub)

        # 示例3：监听错误事件并特殊处理
        def error_listener(event: RuntimeEvent):
            if event.type == "error":
                error_msg = event.data.get("error", "Unknown error")
                def show_error():
                    # 在日志中高亮显示错误
                    from rich.text import Text
                    self.query_one(RichLog).write(Text(f"❌ 错误: {error_msg}", style="bold red"))
                    # 更新状态
                    self._push_status_update(f"错误: {error_msg[:30]}...")
                    self._render_status()
                self.call_from_thread(show_error)

        sub = self._event_bus.subscribe(error_listener, "error")
        self._custom_listeners.append(sub)

    def __del__(self):
        """清理事件处理器和渲染器"""
        if hasattr(self, '_event_handler'):
            self._event_handler.unsubscribe_all()
        if hasattr(self, '_tui_renderer'):
            self._tui_renderer.unsubscribe_all()
        # 清理自定义监听器
        for listener in getattr(self, '_custom_listeners', []):
            self._event_bus.unsubscribe(listener)
        self._custom_listeners = []
        # 清理权限提示状态
        self._showing_permission_prompt = False
        if self._pending_shell_confirm is not None:
            _, ev, result = self._pending_shell_confirm
            result["cancel"] = "Cancelled: TUI closing."
            ev.set()

    def on_unmount(self) -> None:
        """文本 UI 生命周期结束时显式清理订阅。"""
        if hasattr(self, '_event_handler'):
            self._event_handler.unsubscribe_all()
        if hasattr(self, '_tui_renderer'):
            self._tui_renderer.unsubscribe_all()
        for listener in getattr(self, '_custom_listeners', []):
            self._event_bus.unsubscribe(listener)
        self._custom_listeners = []

    def _input_widget(self) -> Input:
        return self.query_one("#input", Input)

    def _push_status_update(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        self._status_updates.append(text)
        if len(self._status_updates) > 3:
            self._status_updates = self._status_updates[-3:]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)

        with Horizontal(id="top"):
            yield Static("", id="top_left")
            yield Static(WELCOME_RIGHT, id="top_right")

        yield Static(
            "",
            id="status_line",
        )

        yield RichLog(id="log", wrap=True, highlight=False, markup=False)
        yield Static("", id="stream", markup=False)
        yield Input(placeholder="Type a message. Use /help.", id="input")
        yield Footer()

    def on_mount(self) -> None:
        if not tracemalloc.is_tracing():
            tracemalloc.start()
        self.set_interval(1.5, self._update_resource_status)
        self._input_widget().focus()
        self._heal_pending_tool_calls()
        self._render_history_bootstrap()
        self._render_loaded_history()
        self._render_top_left()
        self._render_top_right()
        self._render_status()

    def _update_resource_status(self) -> None:
        cpu_s = time.process_time()
        mem_mb = 0.0
        if tracemalloc.is_tracing():
            current_bytes, _peak_bytes = tracemalloc.get_traced_memory()
            mem_mb = current_bytes / (1024 * 1024)
        self._resource_status = f"CPU:{cpu_s:.1f}s MEM:{mem_mb:.1f}MB"
        self._render_status()

    def _render_top_right(self) -> None:
        # Keep tips on the right, and show recent status updates underneath.
        lines: list[str] = [WELCOME_RIGHT.strip()]

        if self._status_updates:
            lines.append("")
            lines.append("Status (latest 3)")
            for s in reversed(self._status_updates[-3:]):
                lines.append(f"- {s}")

        self.query_one("#top_right", Static).update("\n".join(lines).strip() + "\n")

    def _render_loaded_history(self) -> None:
        log = self.query_one(RichLog)

        msgs = self.runtime.messages
        if msgs and msgs[0].role == "system":
            msgs = msgs[1:]

        for msg in msgs:
            if msg.role == "user":
                self._append_user(msg.content)
                continue

            if msg.role == "assistant":
                if (msg.content or "").strip():
                    log.write(msg.content)
                continue

            if msg.role == "tool":
                name = msg.name or "tool"
                content = (msg.content or "").strip()
                if name == "status_update":
                    if content:
                        self._push_status_update(content)
                        self._render_top_right()
                        line = Text("[status] ", style="bold cyan")
                        line.append(content)
                        log.write(line)
                    continue

                log.write(Text(f"[tool:{name}]", style="bold magenta"))
                if content:
                    log.write(content)
                log.write(Text(f"[/tool:{name}]", style="dim"))
                continue

            if msg.role == "system":
                if (msg.content or "").strip():
                    self._append_system(msg.content)

    def _render_status(self) -> None:
        # 如果正在显示权限提示，不更新状态行
        if self._showing_permission_prompt:
            return

        meta = self._session_store.metas.get(self.runtime.session_id)
        title = (meta.title if meta else "Untitled").strip() or "Untitled"
        thinking_status = "🧠" if self._thinking_enabled else ""

        # Get current turn count from session meta
        turn_count = meta.user_turns if meta else 0

        # Calculate current turn in conversation (if available)
        current_turn = 0
        if hasattr(self, '_current_conversation_turn'):
            current_turn = self._current_conversation_turn

        max_turns = self.runtime.settings.max_turns
        turn_info = f"T:{turn_count}/{max_turns}"
        if current_turn > 0:
            turn_info = f"T:{turn_count}/{max_turns} C:{current_turn}/{max_turns}"

        mode = "RUNING" if self._busy else " "
        header = (
            f"{self.runtime.settings.openai_model} · {self.runtime.settings.workspace_root} · "
            f"{title} {thinking_status} · {turn_info} · {mode} · {self._resource_status}"
        )
        self.query_one("#status_line", Static).update(header)

    def _render_permission_prompt(self, command: str) -> None:
        # Keep permission UX out of the chat log to avoid mixing prompts with conversation.
        self._showing_permission_prompt = True

        # 创建更显眼的权限提示
        from rich.panel import Panel
        from rich.align import Align

        # 清理命令显示，确保可读性
        clean_command = command.replace('\n', ' ').replace('\r', '').strip()
        if len(clean_command) > 60:
            clean_command = clean_command[:57] + "..."

        # 创建醒目的提示面板
        prompt_text = Text()
        prompt_text.append("⚠️  SHELL PERMISSION REQUEST ⚠️\n\n", style="bold yellow")
        prompt_text.append("Command to execute:\n", style="bold")
        prompt_text.append(f"  {clean_command}\n\n", style="bold cyan")
        prompt_text.append("Type ", style="")
        prompt_text.append("y", style="bold green")
        prompt_text.append(" to allow or ", style="")
        prompt_text.append("n", style="bold red")
        prompt_text.append(" to deny", style="")

        # 创建居中的面板
        panel = Panel(
            Align.center(prompt_text),
            border_style="yellow",
            title="[bold]Permission Required[/bold]",
            title_align="center"
        )

        # 在状态行显示固定提示
        status_line = Text("🔒 PERMISSION REQUEST: Type 'y' to allow or 'n' to deny", style="bold yellow on dark_red")
        self.query_one("#status_line", Static).update(status_line)

        # 同时在日志中显示完整提示
        self.query_one(RichLog).write(panel)

    def confirm_shell_run(self, command: str) -> str | None:
        """Ask for shell_run permission inside the TUI.

        Called from the worker thread via shell_run's confirm_callback.
        Blocks the worker thread while the UI remains interactive.
        """

        ev = Event()
        result: dict[str, str | None] = {"cancel": "Cancelled by user."}

        def prompt() -> None:
            self._pending_shell_confirm = (command, ev, result)
            self._render_permission_prompt(command)
            self._input_widget().placeholder = "Allow shell_run? Type y or n"
            self._input_widget().focus()

        self.call_from_thread(prompt)
        ev.wait()
        return result["cancel"]

    def _heal_pending_tool_calls(self) -> None:
        """Ensure any assistant tool_calls are followed by matching tool messages.

        If a previous tool execution was interrupted (e.g. blocked waiting for input),
        providers may reject the next request with HTTP 400.
        """

        i = 0
        while i < len(self.runtime.messages):
            msg = self.runtime.messages[i]
            if msg.role != "assistant" or not msg.tool_calls:
                i += 1
                continue

            tool_calls = msg.tool_calls
            provided: set[str] = set()

            j = i + 1
            while j < len(self.runtime.messages) and self.runtime.messages[j].role == "tool":
                tool_call_id = self.runtime.messages[j].tool_call_id
                if tool_call_id:
                    provided.add(tool_call_id)
                j += 1

            missing = [tc for tc in tool_calls if tc.id not in provided]
            for tc in missing:
                tool_msg = ChatMessage(
                    role="tool",
                    content="Cancelled: missing tool response (auto-healed).",
                    tool_call_id=tc.id,
                    name=tc.function.name,
                )
                self.runtime.messages.insert(j, tool_msg)
                self.runtime.transcript.append("model_message", tool_msg.model_dump(exclude_none=True))
                j += 1

            i = j

    def _render_top_left(self) -> None:
        pet_block = _format_pet_block(self._pet)
        logo = _boxed_logo(_GYQ666_LOGO_LINES)
        text = f"{logo}"
        # text = f"{logo}\n\n{pet_block}\n\nCurrent pet: {self._pet.species}\nUse /pets to change."
        self.query_one('#top_left', Static).update(text)

    def _render_history_bootstrap(self) -> None:
        log = self.query_one(RichLog)
        log.write(Text(f"[session_id={self.runtime.session_id}] transcript={self.runtime.transcript.path}", style="dim"))

    def _append_user(self, text: str) -> None:
        line = Text("❯ ", style="bold cyan")
        line.append(text)
        self.query_one(RichLog).write(line)

    def _append_system(self, text: str) -> None:
        self.query_one(RichLog).write(Text(text, style="yellow"))

    def _append_assistant_final(self, text: str) -> None:
        if text.strip():
            self.query_one(RichLog).write(text)

    def _render_tool_call(self, name: str) -> None:
        self.query_one(RichLog).write(Text(f"[tool:{name}]", style="bold magenta"))

    def _render_tool_result(self, name: str, content: str, error: bool) -> None:
        if name == "status_update":
            return
        if content:
            self.query_one(RichLog).write(content)
        self.query_one(RichLog).write(Text(f"[/tool:{name}]", style="dim"))
        if error:
            self.query_one(RichLog).write(Text(f"Error in tool {name}", style="bold red"))

    def _render_thinking(self, thinking: str) -> None:
        if thinking and self._thinking_enabled:
            self.query_one(RichLog).write(Text(f"[thinking] {thinking}", style="dim yellow"))

    def _render_plan(self, plan: list[dict[str, Any]]) -> None:
        from rich.table import Table
        from rich.panel import Panel
        
        table = Table.grid(expand=True)
        table.add_column(width=4)
        table.add_column()
        
        for i, item in enumerate(plan, 1):
            status = "✅" if item.get("completed") else "⏳"
            text = item.get("text", "")
            tool = f" [dim]({item.get('tool')})[/dim]" if item.get("tool") else ""
            table.add_row(status, f"{text}{tool}")
            
        panel = Panel(
            table, 
            title="[bold blue]Execution Plan[/bold blue]", 
            border_style="blue",
            padding=(0, 1)
        )
        
        # We update the stream area or just write to log
        # For now, let's write to log but we might want a persistent area
        self.query_one(RichLog).write(panel)

    def _render_error(self, error_msg: str) -> None:
        self.query_one(RichLog).write(Text(f"[error] {error_msg}", style="bold red"))

    def _render_status_message(self, status_msg: str) -> None:
        line = Text("[status] ", style="bold cyan")
        line.append(status_msg)
        self.query_one(RichLog).write(line)

    def _handle_permission_request(self, tool_name: str, arguments: dict[str, str]) -> None:
        if tool_name == "shell_run":
            command = arguments.get("command", "")
            if command:
                self.confirm_shell_run(command)

    def _render_debug_event(self, event_type: str) -> None:
        self.query_one(RichLog).write(Text(f"[event:{event_type}]", style="dim"))

    def _stream_delta(self, delta: str) -> None:
        # Called from worker thread via call_from_thread
        if self._assistant_stream_buffer is None:
            self._assistant_stream_buffer = ""
            self.query_one(RichLog).write(Text("────────────────────────────────", style="dim"))

        # 添加delta到缓冲区
        self._assistant_stream_buffer += delta

        # 只在缓冲区达到一定长度或收到完整单词时更新显示
        # 减少频繁更新造成的闪烁
        should_update = (
            len(self._assistant_stream_buffer) < 20 or  # 初始阶段频繁更新
            delta.endswith(' ') or  # 单词结束
            delta.endswith('\n') or  # 换行
            delta.endswith('.') or delta.endswith(',') or  # 标点
            delta.endswith('?') or delta.endswith('!')
        )

        if should_update:
            # 清理可能的控制字符
            clean_buffer = self._assistant_stream_buffer.replace('\r', '')
            self.query_one("#stream", Static).update(clean_buffer)

    def _reset_stream(self) -> None:
        # 如果有缓冲区内容，先写入日志
        if self._assistant_stream_buffer and self._assistant_stream_buffer.strip():
            clean_content = self._assistant_stream_buffer.replace('\r', '').strip()
            if clean_content:
                self.query_one(RichLog).write(clean_content)

        # 重置缓冲区
        self._assistant_stream_buffer = None
        self.query_one("#stream", Static).update("")

    def _handle_slash(self, line: str) -> bool:
        parts = line.strip().split(" ", 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in {"/exit", "/quit"}:
            self.exit()
            return True

        if cmd == "/clear":
            self._pending_clear_confirm = True
            self._append_system("Confirm clear current session history? Type y or n.")
            self._input_widget().placeholder = "Confirm /clear? Type y or n"
            self._input_widget().focus()
            self._render_status()
            return True

        if cmd == "/clear-screen":
            self.query_one(RichLog).clear()
            self.query_one("#stream", Static).update("")
            self._assistant_stream_buffer = None
            self._render_history_bootstrap()
            return True

        if cmd == "/help":
            self._append_system("Commands: /clear, /clear-screen, /help, /exit, /pets, /session, /thinking_toggle")
            self._append_system("/clear will clear transcript + in-memory messages for current session.")
            self._append_system("/thinking_toggle will toggle thinking/reasoning output.")
            return True

        if cmd == "/thinking_toggle":
            self._thinking_enabled = not self._thinking_enabled
            status = "enabled" if self._thinking_enabled else "disabled"
            self._append_system(f"Thinking/reasoning output {status}.")
            self._render_status()
            return True

        if cmd == "/session":
            return self._handle_session_command(arg)

        if cmd == "/pets":
            if not arg:
                names = ", ".join(list_species())
                self._append_system(f"Available pets: {names}")
                self._append_system(f"Current pet: {self._pet.species}")
                self._append_system("Usage: /pets <name>")
                return True

            name = arg.lower()
            if name not in list_species():
                self._append_system(f"Unknown pet '{name}'. Use /pets to list.")
                return True

            self._pet = PetBones(species=name)  # type: ignore[arg-type]
            self._render_top_left()
            self._append_system(f"Switched pet to {name}.")
            return True

        self._append_system("Unknown command. Use /help")
        return True

    def _handle_session_command(self, arg: str) -> bool:
        if self._busy:
            self._append_system("Busy running a query; wait before switching sessions.")
            return True

        transcript_dir = self.runtime.settings.resolved_transcript_dir()
        defaults = default_sessions(workspace_root=self.runtime.settings.workspace_root, transcript_dir=transcript_dir)

        sessions = self._session_store.list_sessions(defaults)

        if not arg or arg.lower() in {"list", "ls"}:
            self._append_system(f"Current session: {self.runtime.session_id}")
            self._append_system(f"Defaults: chat={defaults.chat} repl={defaults.repl} tui={defaults.tui}")
            if sessions:
                self._append_system("Sessions:")
                for idx, sid in enumerate(sessions, start=1):
                    title = self._session_store.title_for_list(sid)
                    label = sid
                    if sid == defaults.repl:
                        label = "repl"
                    elif sid == defaults.chat:
                        label = "chat"
                    elif sid == defaults.tui:
                        label = "tui"
                    self._append_system(f"  {idx}) {label} — {title}")
            else:
                self._append_system("Sessions: (none)")

            self._append_system("Usage: /session chat | /session repl | /session <number>")
            return True

        target = arg.strip()
        if target.isdigit():
            idx = int(target)
            if idx < 1 or idx > len(sessions):
                self._append_system(f"Invalid session number {idx}. Use /session to list.")
                return True
            target = sessions[idx - 1]
        else:
            if target.lower() == "chat":
                target = defaults.chat
            elif target.lower() == "repl":
                target = defaults.repl
            elif target.lower() == "tui":
                target = defaults.tui
            else:
                self._append_system("Use /session chat, /session repl, /session tui, or /session <number>.")
                return True

        self._switch_session(target)
        return True

    def _switch_session(self, session_id: str) -> None:
        loaded = switch_runtime_session(self.runtime, session_id=session_id)

        # Ensure meta exists
        self._session_store.ensure_saved(session_id)

        self.query_one(RichLog).clear()
        self.query_one("#stream", Static).update("")
        self._assistant_stream_buffer = None
        self._heal_pending_tool_calls()
        self._render_history_bootstrap()
        self._render_loaded_history()
        self._render_status()
        self._append_system(f"Switched session to {session_id} (loaded {loaded} messages).")

    def _clear_current_session_history(self) -> None:
        if self._busy:
            self._append_system("Busy running a query; wait before clearing history.")
            return

        reset_runtime_history(self.runtime)

        self._session_store.clear_session(self.runtime.session_id)

        self.query_one(RichLog).clear()
        self.query_one("#stream", Static).update("")
        self._assistant_stream_buffer = None
        self._render_history_bootstrap()
        self._render_status()
        self._append_system(f"Cleared current session history: {self.runtime.session_id}")

    def _submit_text(self, text: str) -> None:
        if not text.strip():
            return

        if self._pending_shell_confirm is not None:
            command, ev, result = self._pending_shell_confirm
            answer = text.strip().lower()

            # 重置权限提示标志
            self._showing_permission_prompt = False

            if answer in {"y", "yes"}:
                result["cancel"] = None
                # 在日志中显示允许结果
                from rich.panel import Panel
                from rich.align import Align
                from rich.text import Text as RichText

                allowed_text = RichText()
                allowed_text.append("✅ PERMISSION GRANTED\n\n", style="bold green")
                allowed_text.append("Command executed:\n", style="bold")
                allowed_text.append(f"  {command}\n", style="cyan")

                panel = Panel(
                    Align.center(allowed_text),
                    border_style="green",
                    title="[bold]Permission Granted[/bold]",
                    title_align="center"
                )
                self.query_one(RichLog).write(panel)
            else:
                result["cancel"] = "Cancelled by user."
                # 在日志中显示拒绝结果
                from rich.panel import Panel
                from rich.align import Align
                from rich.text import Text as RichText

                denied_text = RichText()
                denied_text.append("❌ PERMISSION DENIED\n\n", style="bold red")
                denied_text.append("Command blocked:\n", style="bold")
                denied_text.append(f"  {command}\n", style="cyan")
                denied_text.append("\nUser cancelled the operation.", style="dim")

                panel = Panel(
                    Align.center(denied_text),
                    border_style="red",
                    title="[bold]Permission Denied[/bold]",
                    title_align="center"
                )
                self.query_one(RichLog).write(panel)

            self._pending_shell_confirm = None
            self._input_widget().placeholder = "Type a message. Use /help."
            self._render_status()
            ev.set()
            return

        if self._pending_clear_confirm:
            answer = text.strip().lower()
            if answer in {"y", "yes"}:
                self._pending_clear_confirm = False
                self._input_widget().placeholder = "Type a message. Use /help."
                self._clear_current_session_history()
                return
            if answer in {"n", "no"}:
                self._pending_clear_confirm = False
                self._input_widget().placeholder = "Type a message. Use /help."
                self._append_system("Cancelled /clear.")
                self._render_status()
                return

            self._append_system("Please answer y or n.")
            self._input_widget().placeholder = "Confirm /clear? Type y or n"
            return

        if text.startswith("/"):
            self._handle_slash(text)
            return

        self._append_user(text)
        self._reset_stream()
        self._busy = True
        turn_no = self._session_store.increment_user_turn(self.runtime.session_id)
        # Generate / refresh title on turn 1, 51, 101, ... based on this turn's first message.
        should_title = (turn_no - 1) % 50 == 0
        # Reset current conversation turn
        self._current_conversation_turn = 0
        self._render_status()
        self._run_query_in_worker(text, turn_no=turn_no, title_seed=text if should_title else None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.rstrip("\n")
        # 彻底清理输入框，包括任何隐藏的控制字符
        self._input_widget().value = ""
        # 确保输入框状态重置
        self._input_widget().placeholder = "Type a message. Use /help."
        self._submit_text(text)

    def action_copy_input(self) -> None:
        self._input_widget().action_copy()

    def action_paste_input(self) -> None:
        self._input_widget().action_paste()

    def action_clear_screen(self) -> None:
        self.query_one(RichLog).clear()
        self.query_one("#stream", Static).update("")
        self._assistant_stream_buffer = None
        self._render_history_bootstrap()

    def action_scroll_log_up(self) -> None:
        self.query_one(RichLog).action_scroll_up()

    def action_scroll_log_down(self) -> None:
        self.query_one(RichLog).action_scroll_down()

    @work(thread=True, exclusive=True)
    def _run_query_in_worker(self, user_text: str, *, turn_no: int, title_seed: str | None) -> None:
        def publish_local(event_type: RuntimeEventType, data: dict) -> None:
            self._event_bus.publish(RuntimeEvent(type=cast(RuntimeEventType, event_type), data=data))

        # 使用基础事件处理器发布助手增量输出
        def printer(delta: str) -> None:
            publish_local("assistant_delta", {"delta": delta})

        # 使用基础事件处理器发布工具输出
        def tool_printer(name: str, output: str) -> None:
            if name == "status_update":
                publish_local("status", {"message": output})
                return

            publish_local("tool_call", {"name": name, "function": {"name": name}})
            publish_local(
                "tool_result",
                {
                    "name": name,
                    "content": output,
                    "error": output.startswith("Tool error:"),
                },
            )

        if title_seed is not None:
            try:
                title = self._generate_title_from_seed(title_seed)
            except Exception:
                title = None

            if title:
                self._session_store.set_title(self.runtime.session_id, title=title, title_gen_turn=turn_no)

                # 发布会话更新事件
                session_state = SessionState(
                    session_id=self.runtime.session_id,
                    title=title,
                    user_turns=turn_no,
                    current_turn=self._current_conversation_turn,
                    max_turns=self.runtime.settings.max_turns,
                    thinking_enabled=self._thinking_enabled
                )
                publish_local("session_update", session_state.to_dict())

        try:
            # 直接创建ToolContext，因为参数很简单
            tool_context = ToolContext(
                session_id=self.runtime.session_id,
                transcript=self.runtime.transcript,
                workspace_root=self.runtime.settings.workspace_root,
            )
            result = run_query(
                client=self.runtime.client,
                registry=self.runtime.registry,
                transcript=self.runtime.transcript,
                messages=self.runtime.messages,
                user_text=user_text,
                max_turns=self.runtime.settings.max_turns,
                stream_printer=printer,
                tool_printer=tool_printer,
                tool_context=tool_context,
                tool_limits=ToolLimits(
                    max_tool_calls=self.runtime.settings.max_tool_calls,
                    max_tool_calls_per_tool=self.runtime.settings.max_tool_calls_per_tool,
                    max_tool_calls_same_args=self.runtime.settings.max_tool_calls_same_args,
                ),
                thinking_enabled=self._thinking_enabled,
            )

            # 使用增强的事件消费函数
            consume_runtime_events(
                result.events,
                on_turn_update=lambda data: publish_local(
                    "turn_update",
                    {
                        "current_turn": int(data.get("current_turn") or 0),
                        "max_turns": self.runtime.settings.max_turns,
                    },
                ),
                on_turn_complete=lambda data: publish_local(
                    "turn_complete",
                    {"turns_used": int(data.get("turns_used") or result.turns_used)},
                ),
                on_provider_error=lambda data: publish_local(
                    "error",
                    {"error": data.get("error", "unknown")},
                ),
                on_thinking=lambda data: publish_local(
                    "thinking",
                    {"thinking": data.get("thinking", "")},
                ),
            )

            # 发布最终结果
            for msg in reversed(self.runtime.messages):
                if msg.role == "assistant" and msg.content:
                    publish_local("assistant_final", {"content": msg.content})
                    break

            publish_local("turn_complete", {"turns_used": result.turns_used})

        except Exception as e:
            # 发布错误事件
            publish_local("error", {"error": f"{type(e).__name__}: {e}"})
            return

        def finalize() -> None:
            self.query_one("#stream", Static).update("")
            self._busy = False
            # 更新状态
            self._render_status()

        self.call_from_thread(finalize)

    def _generate_title_from_seed(self, seed: str) -> str | None:
        seed = (seed or "").strip()
        if not seed:
            return None

        prompt = (
            "Generate a short, human-friendly title for this conversation based on the user's message. "
            "Output ONLY the title. Keep it under 40 characters if possible."
        )

        final = self.runtime.client.complete(
            messages=[
                ChatMessage(role="system", content=prompt),
                ChatMessage(role="user", content=seed),
            ],
            tools=None,
        )
        title = (final.content or "").strip()
        # Take first line only.
        title = title.splitlines()[0].strip() if title else ""
        if not title:
            # Fallback to a truncated version of the seed.
            title = " ".join(seed.split())
            title = title[:40] + ("..." if len(title) > 40 else "")
        return title


def run_tui(*, resume: str | None = None, workspace_root: Path | None = None) -> None:
    app_session = create_app_session(
        workspace_root=workspace_root,
        resume=resume,
        default_session_name="tui",
        prefer_recent=True,
    )
    settings = app_session.settings
    session_id = app_session.session_id
    transcript = app_session.transcript

    confirm_holder: dict[str, Callable[[str], str | None]] = {}

    def shell_confirm_callback(cmd: str) -> str | None:
        cb = confirm_holder.get("cb")
        if cb is None:
            return "Cancelled: TUI not ready for confirmation."
        return cb(cmd)

    bootstrap = create_agent_bootstrap(
        settings=settings,
        session_id=session_id,
        transcript=transcript,
        mode="tui",
        shell_confirm_callback=shell_confirm_callback if settings.shell_confirm else None,
    )
    runtime = bootstrap.runtime

    try:
        app = GGbotTui(runtime)
        confirm_holder["cb"] = app.confirm_shell_run
        app.run()
    finally:
        bootstrap.client.close()
