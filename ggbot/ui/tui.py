from __future__ import annotations

import json
import time
import tracemalloc
import uuid
from pathlib import Path
from threading import Event
from collections.abc import Callable

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Footer, Header, Input, RichLog, Static

from ..core.sessions import default_sessions
from ..core.agent_loop import run_query
from ..core.agent_loop import ToolLimits
from ..core.runtime import (
    AgentRuntime,
    create_agent_bootstrap,
    create_app_session,
    ensure_message_bootstrap,
    reset_runtime_history,
    switch_runtime_session,
)
from ..core.runtime_events import consume_runtime_events
from ..core.session_store import SessionStore
from ..core.transcript import Transcript
from ..core.types import ChatMessage
from ..tools.context import ToolContext
from .pets import PetBones, Species, list_species, render_sprite


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

        mode = "RUN" if self._busy else "IDLE"
        header = (
            f"{self.runtime.settings.openai_model} · {self.runtime.settings.workspace_root} · "
            f"{title} {thinking_status} · {turn_info} · {mode} · {self._resource_status}"
        )
        self.query_one("#status_line", Static).update(header)

    def _render_permission_prompt(self, command: str) -> None:
        # Keep permission UX out of the chat log to avoid mixing prompts with conversation.
        line = Text("[permission] ", style="bold yellow")
        line.append("Allow shell_run? ")
        line.append(command, style="bold")
        line.append(" (y/n)")
        self.query_one("#status_line", Static).update(line)

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

    def _stream_delta(self, delta: str) -> None:
        # Called from worker thread via call_from_thread
        if self._assistant_stream_buffer is None:
            self._assistant_stream_buffer = ""
            self.query_one(RichLog).write(Text("────────────────────────────────", style="dim"))
        self._assistant_stream_buffer += delta

        # RichLog doesn't support in-place editing. Instead we render the current
        # assistant stream in a dedicated widget that we update.
        self.query_one("#stream", Static).update(self._assistant_stream_buffer)

    def _reset_stream(self) -> None:
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
            if answer in {"y", "yes"}:
                result["cancel"] = None
                line = Text("[permission] ", style="bold yellow")
                line.append("Allowed: ", style="green")
                line.append(command, style="bold")
                self.query_one(RichLog).write(line)
            else:
                result["cancel"] = "Cancelled by user."
                line = Text("[permission] ", style="bold yellow")
                line.append("Denied: ", style="red")
                line.append(command, style="bold")
                self.query_one(RichLog).write(line)

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
        self._input_widget().value = ""
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
        def printer(delta: str) -> None:
            self.call_from_thread(self._stream_delta, delta)

        def tool_printer(name: str, output: str) -> None:
            def write() -> None:
                out = (output or "").strip()
                if name == "status_update":
                    if out:
                        self._push_status_update(out)
                        self._render_status()
                        self._render_top_right()
                        line = Text("[status] ", style="bold cyan")
                        line.append(out)
                        self.query_one(RichLog).write(line)
                    return

                self.query_one(RichLog).write(Text(f"[tool:{name}]", style="bold magenta"))
                if out:
                    self.query_one(RichLog).write(out)
                self.query_one(RichLog).write(Text(f"[/tool:{name}]", style="dim"))

            self.call_from_thread(write)

        if title_seed is not None:
            try:
                title = self._generate_title_from_seed(title_seed)
            except Exception:
                title = None

            if title:
                self._session_store.set_title(self.runtime.session_id, title=title, title_gen_turn=turn_no)

                def update_title() -> None:
                    self._render_status()

                self.call_from_thread(update_title)

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
            consume_runtime_events(
                result.events,
                on_turn_update=lambda data: setattr(self, "_current_conversation_turn", int(data.get("current_turn") or 0)),
                on_turn_complete=lambda data: setattr(self, "_current_conversation_turn", int(data.get("turns_used") or result.turns_used)),
                on_provider_error=lambda data: self.call_from_thread(
                    lambda: self._append_system(f"Provider error: {data.get('error', 'unknown')}")
                ),
            )
            self._current_conversation_turn = result.turns_used
        except Exception as e:
            def write_error() -> None:
                self.query_one(RichLog).write(f"[error] {type(e).__name__}: {e}")
                self.query_one("#stream", Static).update("")
                self._busy = False

            self.call_from_thread(write_error)
            return

        def finalize() -> None:
            self.query_one("#stream", Static).update("")
            for msg in reversed(self.runtime.messages):
                if msg.role == "assistant":
                    self._append_assistant_final(msg.content or "")
                    break
            self._busy = False
            # Update status with final turn count
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
