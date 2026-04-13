from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from collections.abc import Callable

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Footer, Header, Input, RichLog, Static

from ..core.config import Settings
from ..prompts import PromptManager
from ..core.session_meta import (
    SessionMeta,
    increment_user_turn,
    load_all as load_session_meta,
    save_all as save_session_meta,
    set_title as set_session_title,
)
from ..core.sessions import default_sessions
from ..core.agent_loop import run_query
from ..core.agent_loop import ToolLimits
from ..core.transcript import Transcript, clear_transcript, load_model_messages, open_session
from ..core.types import ChatMessage
from ..core.client_factory import make_llm_client
from ..providers.types import ChatCompletionClient
from ..tools.manager import create_tool_manager
from ..tools.context import ToolContext
from ..tools.registry import ToolRegistry
from .pets import PetBones, Species, list_species, render_sprite


def _new_session_id() -> str:
    return uuid.uuid4().hex


def _most_recent_session_id(transcript_dir: Path) -> str | None:
    candidates = list(transcript_dir.glob("*.jsonl"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0].stem


def _default_system_message() -> ChatMessage:
    return ChatMessage(
        role="system",
        content=(
            "You are GGbot, a helpful coding CLI agent. "
            "Use available tools when needed. "
            "When using tools, be concise and safe."
        ),
    )




def _ensure_message_bootstrap(
    messages: list[ChatMessage],
    transcript: Transcript,
    *,
    system_message: ChatMessage | None = None,
) -> None:
    if messages and messages[0].role == "system":
        return
    msg = system_message or _default_system_message()
    messages.insert(0, msg)
    transcript.append("model_message", msg.model_dump(exclude_none=True))


@dataclass
class _Runtime:
    settings: Settings
    session_id: str
    transcript: Transcript
    messages: list[ChatMessage]
    system_message: ChatMessage
    registry: ToolRegistry
    client: ChatCompletionClient


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
        height: 3;
        padding: 0 1;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self, runtime: _Runtime) -> None:
        super().__init__()
        self.runtime = runtime
        self._assistant_stream_buffer: str | None = None
        self._pet: PetBones = PetBones(species='duck')
        self._pending_shell_confirm: tuple[str, Event, dict[str, str | None]] | None = None
        self._pending_clear_confirm: bool = False
        self._busy: bool = False
        self._status_updates: list[str] = []
        self._transcript_dir = self.runtime.settings.resolved_transcript_dir()
        self._session_meta: dict[str, SessionMeta] = load_session_meta(self._transcript_dir)
        if self.runtime.session_id not in self._session_meta:
            self._session_meta[self.runtime.session_id] = SessionMeta(session_id=self.runtime.session_id)
            save_session_meta(self._transcript_dir, self._session_meta)

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
        self.query_one(Input).focus()
        self._heal_pending_tool_calls()
        self._render_history_bootstrap()
        self._render_loaded_history()
        self._render_top_left()
        self._render_top_right()
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
        meta = self._session_meta.get(self.runtime.session_id)
        title = (meta.title if meta else "Untitled").strip() or "Untitled"
        header = f"{self.runtime.settings.openai_model} · {self.runtime.settings.workspace_root} · {title}"
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
            self.query_one(Input).placeholder = "Allow shell_run? Type y or n"
            self.query_one(Input).focus()

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
            self.query_one(Input).placeholder = "Confirm /clear? Type y or n"
            self.query_one(Input).focus()
            self._render_status()
            return True

        if cmd == "/clear-screen":
            self.query_one(RichLog).clear()
            self.query_one("#stream", Static).update("")
            self._assistant_stream_buffer = None
            self._render_history_bootstrap()
            return True

        if cmd == "/help":
            self._append_system("Commands: /clear, /clear-screen, /help, /exit, /pets, /session")
            self._append_system("/clear will clear transcript + in-memory messages for current session.")
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

        transcript_dir = self._transcript_dir
        defaults = default_sessions(workspace_root=self.runtime.settings.workspace_root, transcript_dir=transcript_dir)

        sessions = self._list_sessions(defaults)

        if not arg or arg.lower() in {"list", "ls"}:
            self._append_system(f"Current session: {self.runtime.session_id}")
            self._append_system(f"Defaults: chat={defaults.chat} repl={defaults.repl} tui={defaults.tui}")
            if sessions:
                self._append_system("Sessions:")
                for idx, sid in enumerate(sessions, start=1):
                    title = self._session_title_for_list(sid)
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

    def _list_sessions(self, defaults) -> list[str]:
        transcript_dir = self._transcript_dir
        existing = [p.stem for p in transcript_dir.glob("*.jsonl")]
        # Prefer most recently modified first.
        def mtime(sid: str) -> float:
            p = transcript_dir / f"{sid}.jsonl"
            try:
                return p.stat().st_mtime
            except Exception:
                return 0.0

        existing_sorted = sorted(existing, key=mtime, reverse=True)
        # Ensure defaults are always first.
        out: list[str] = []
        for sid in (defaults.repl, defaults.chat, defaults.tui):
            if sid not in out:
                out.append(sid)
        for sid in existing_sorted:
            if sid not in out:
                out.append(sid)
        return out

    def _first_user_message(self, session_id: str) -> str | None:
        path = self._transcript_dir / f"{session_id}.jsonl"
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except Exception:
                        continue
                    if ev.get("type") != "model_message":
                        continue
                    data = ev.get("data") or {}
                    if not isinstance(data, dict):
                        continue
                    if data.get("role") == "user" and data.get("content"):
                        return str(data.get("content"))
        except Exception:
            return None
        return None

    def _session_title_for_list(self, session_id: str) -> str:
        meta = self._session_meta.get(session_id)
        if meta is not None and meta.title:
            return meta.title
        first = self._first_user_message(session_id)
        if first:
            first = " ".join(first.strip().split())
            return first[:60] + ("..." if len(first) > 60 else "")
        return "Untitled"

    def _switch_session(self, session_id: str) -> None:
        transcript_dir = self._transcript_dir
        session = open_session(transcript_dir=transcript_dir, session_id=session_id)
        transcript = Transcript(path=session.path)
        messages = load_model_messages(transcript)
        _ensure_message_bootstrap(messages, transcript, system_message=self.runtime.system_message)

        self.runtime.session_id = session_id
        self.runtime.transcript = transcript
        self.runtime.messages = messages

        # Ensure meta exists
        if session_id not in self._session_meta:
            self._session_meta = load_session_meta(self._transcript_dir)
        if session_id not in self._session_meta:
            self._session_meta[session_id] = SessionMeta(session_id=session_id)
            save_session_meta(self._transcript_dir, self._session_meta)

        self.query_one(RichLog).clear()
        self.query_one("#stream", Static).update("")
        self._assistant_stream_buffer = None
        self._heal_pending_tool_calls()
        self._render_history_bootstrap()
        self._render_loaded_history()
        self._render_status()
        self._append_system(f"Switched session to {session_id} (loaded {len(messages)} messages).")

    def _clear_current_session_history(self) -> None:
        if self._busy:
            self._append_system("Busy running a query; wait before clearing history.")
            return

        clear_transcript(self.runtime.transcript)
        self.runtime.messages = []
        _ensure_message_bootstrap(
            self.runtime.messages,
            self.runtime.transcript,
            system_message=self.runtime.system_message,
        )

        self._session_meta[self.runtime.session_id] = SessionMeta(session_id=self.runtime.session_id)
        save_session_meta(self._transcript_dir, self._session_meta)

        self.query_one(RichLog).clear()
        self.query_one("#stream", Static).update("")
        self._assistant_stream_buffer = None
        self._render_history_bootstrap()
        self._render_status()
        self._append_system(f"Cleared current session history: {self.runtime.session_id}")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.rstrip("\n")
        self.query_one(Input).value = ""
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
            self.query_one(Input).placeholder = "Type a message. Use /help."
            self._render_status()
            ev.set()
            return

        if self._pending_clear_confirm:
            answer = text.strip().lower()
            if answer in {"y", "yes"}:
                self._pending_clear_confirm = False
                self.query_one(Input).placeholder = "Type a message. Use /help."
                self._clear_current_session_history()
                return
            if answer in {"n", "no"}:
                self._pending_clear_confirm = False
                self.query_one(Input).placeholder = "Type a message. Use /help."
                self._append_system("Cancelled /clear.")
                self._render_status()
                return

            self._append_system("Please answer y or n.")
            self.query_one(Input).placeholder = "Confirm /clear? Type y or n"
            return

        if text.startswith("/"):
            self._handle_slash(text)
            return

        self._append_user(text)
        self._reset_stream()
        self._busy = True
        turn_no = increment_user_turn(self._session_meta, self.runtime.session_id)
        save_session_meta(self._transcript_dir, self._session_meta)
        # Generate / refresh title on turn 1, 51, 101, ... based on this turn's first message.
        should_title = (turn_no - 1) % 50 == 0
        self._run_query_in_worker(text, turn_no=turn_no, title_seed=text if should_title else None)

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
                set_session_title(self._session_meta, self.runtime.session_id, title=title, title_gen_turn=turn_no)
                save_session_meta(self._transcript_dir, self._session_meta)

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
            run_query(
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
            )
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
    settings = Settings.load(workspace_root=workspace_root)
    if workspace_root is not None:
        settings.workspace_root = workspace_root

    defaults = default_sessions(
        workspace_root=settings.workspace_root,
        transcript_dir=settings.resolved_transcript_dir(),
    )
    if resume is not None:
        session_id = resume
    else:
        recent = _most_recent_session_id(settings.resolved_transcript_dir())
        session_id = recent or defaults.tui
    session = open_session(transcript_dir=settings.resolved_transcript_dir(), session_id=session_id)
    transcript = Transcript(path=session.path)

    registry = ToolRegistry()
    confirm_holder: dict[str, Callable[[str], str | None]] = {}

    def shell_confirm_callback(cmd: str) -> str | None:
        cb = confirm_holder.get("cb")
        if cb is None:
            return "Cancelled: TUI not ready for confirmation."
        return cb(cmd)

    # 使用新的ToolManager
    tool_manager = create_tool_manager(
        settings,
        shell_confirm_callback=shell_confirm_callback if settings.shell_confirm else None,
    )
    registry = tool_manager.registry

    prompt_manager = PromptManager(settings=settings)
    system_message = prompt_manager.build_system_message(
        mode="tui",
        tool_specs=registry.specs(),
    )

    messages = load_model_messages(transcript)
    _ensure_message_bootstrap(messages, transcript, system_message=system_message)

    client = make_llm_client(settings)

    runtime = _Runtime(
        settings=settings,
        session_id=session_id,
        transcript=transcript,
        messages=messages,
        system_message=system_message,
        registry=registry,
        client=client,
    )

    try:
        app = GGbotTui(runtime)
        confirm_holder["cb"] = app.confirm_shell_run
        app.run()
    finally:
        client.close()
