from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import typer

from ggbot.core.config import Settings
from ggbot.core.client_factory import make_llm_client
from ggbot.prompts import PromptManager
from ggbot.core.sessions import default_sessions
from ggbot.core.agent_loop import ToolLimits, run_query
from ggbot.tools.manager import create_tool_manager
from ggbot.tools.context import ToolContext
from ggbot.tools.registry import ToolRegistry
from ggbot.core.transcript import Transcript, load_model_messages, open_session
from ggbot.core.types import ChatMessage

# ANSI color codes for log highlighting
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_DIM = "\033[2m"
COLOR_RED = "\033[31m"
COLOR_GREEN = "\033[32m"
COLOR_YELLOW = "\033[33m"
COLOR_BLUE = "\033[34m"
COLOR_MAGENTA = "\033[35m"
COLOR_CYAN = "\033[36m"
COLOR_WHITE = "\033[37m"

app = typer.Typer(add_completion=False, help="GGbot - minimal CLI agent")


@app.callback()
def _main(
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Show pretty Rich tracebacks (includes locals) on crashes.",
    ),
) -> None:
    if not debug:
        return

    from rich.traceback import install

    install(show_locals=True)


def _default_system_message() -> ChatMessage:
    return ChatMessage(
        role="system",
        content=(
            "You are GGbot, a helpful coding CLI agent. "
            "Use available tools when needed. "
            "When using tools, be concise and safe."
        ),
    )


def _print_delta(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def _print_tool_output(name: str, output: str) -> None:
    print("")
    print(f"[tool:{name}]")
    print(output)
    print(f"[/tool:{name}]")


def _most_recent_session_id(transcript_dir: Path) -> str | None:
    candidates = list(transcript_dir.glob("*.jsonl"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0].stem


def _format_ts(ts_ms: int | None) -> str:
    if ts_ms is None:
        return "--:--:--"
    try:
        return datetime.fromtimestamp(ts_ms / 1000).strftime("%H:%M:%S")
    except Exception:
        return "--:--:--"


def _parse_ts_ms(raw: object) -> int | None:
    if isinstance(raw, (int, float)):
        return int(raw)
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return None


def _render_event_line(
    ev: dict,
    *,
    include_system: bool,
    include_events: bool,
) -> str | None:
    event_type = str(ev.get("type") or "")
    ts_ms = _parse_ts_ms(ev.get("ts_ms"))

    if event_type == "model_message":
        data = ev.get("data") or {}
        try:
            msg = ChatMessage.model_validate(data)
        except Exception:
            return None

        if not include_system and msg.role == "system":
            return None
        return _render_log_message(msg, ts_ms=ts_ms)

    if not include_events:
        return None

    data = ev.get("data") or {}
    ts_prefix = f"{COLOR_DIM}[{_format_ts(ts_ms)}]{COLOR_RESET} "

    if event_type == "tool_call":
        name = str(data.get("name") or "<unknown>")
        if data.get("arguments") is not None:
            args_text = json.dumps(data.get("arguments"), ensure_ascii=False)
        else:
            args_text = str(data.get("raw_arguments") or "{}")
        return f"{ts_prefix}{COLOR_YELLOW}[EVENT]{COLOR_RESET} {COLOR_BLUE}tool_call{COLOR_RESET} name={COLOR_CYAN}{name}{COLOR_RESET} args={args_text}"

    if event_type == "tool_result":
        name = str(data.get("name") or "<unknown>")
        status = "error" if bool(data.get("error")) else "ok"
        status_color = COLOR_RED if status == "error" else COLOR_GREEN
        auto_healed = " auto_healed=true" if bool(data.get("auto_healed")) else ""
        content_len = int(data.get("content_len") or 0)
        return (
            f"{ts_prefix}{COLOR_YELLOW}[EVENT]{COLOR_RESET} {COLOR_BLUE}tool_result{COLOR_RESET} "
            f"name={COLOR_CYAN}{name}{COLOR_RESET} status={status_color}{status}{COLOR_RESET} "
            f"content_len={COLOR_MAGENTA}{content_len}{COLOR_RESET}{auto_healed}"
        )

    if event_type == "provider_error":
        err = str(data.get("error") or "unknown")
        return f"{ts_prefix}{COLOR_YELLOW}[EVENT]{COLOR_RESET} {COLOR_RED}provider_error{COLOR_RESET} {err}"

    if event_type == "status":
        msg = str(data.get("message") or "")
        stage = data.get("stage")
        percent = data.get("percent")

        extras: list[str] = []
        if stage is not None:
            extras.append(f"stage={stage}")
        if percent is not None:
            extras.append(f"percent={percent}")

        extra_text = (" " + " ".join(extras)) if extras else ""
        return f"{ts_prefix}{COLOR_YELLOW}[EVENT]{COLOR_RESET} {COLOR_MAGENTA}status{COLOR_RESET}{extra_text} {msg}"

    if event_type == "tool_stream":
        name = str(data.get("name") or "<unknown>")
        chunk = str(data.get("chunk") or "")
        chunk = chunk.replace("\r", "")
        if len(chunk) > 200:
            chunk = chunk[:200] + "…"
        return f"{ts_prefix}{COLOR_YELLOW}[EVENT]{COLOR_RESET} {COLOR_BLUE}tool_stream{COLOR_RESET} name={COLOR_CYAN}{name}{COLOR_RESET} chunk={COLOR_DIM}{chunk!r}{COLOR_RESET}"

    if event_type == "turn_info":
        max_turns = int(data.get("max_turns") or 0)
        start_turn = int(data.get("start_turn") or 0)
        return f"{ts_prefix}{COLOR_YELLOW}[EVENT]{COLOR_RESET} {COLOR_GREEN}turn_info{COLOR_RESET} max_turns={COLOR_CYAN}{max_turns}{COLOR_RESET} start_turn={COLOR_CYAN}{start_turn}{COLOR_RESET}"

    if event_type == "turn_update":
        current_turn = int(data.get("current_turn") or 0)
        max_turns = int(data.get("max_turns") or 0)
        progress = f"{current_turn}/{max_turns}"
        progress_color = COLOR_GREEN if current_turn < max_turns else COLOR_YELLOW
        return f"{ts_prefix}{COLOR_YELLOW}[EVENT]{COLOR_RESET} {COLOR_GREEN}turn_update{COLOR_RESET} turn={progress_color}{progress}{COLOR_RESET}"

    if event_type == "turn_complete":
        turns_used = int(data.get("turns_used") or 0)
        max_turns = int(data.get("max_turns") or 0)
        completed = bool(data.get("completed"))
        status = "completed" if completed else "max_turns_reached"
        status_color = COLOR_GREEN if completed else COLOR_YELLOW
        return f"{ts_prefix}{COLOR_YELLOW}[EVENT]{COLOR_RESET} {COLOR_GREEN}turn_complete{COLOR_RESET} turns_used={COLOR_CYAN}{turns_used}{COLOR_RESET}/{COLOR_CYAN}{max_turns}{COLOR_RESET} status={status_color}{status}{COLOR_RESET}"

    return None


def _iter_rendered_log_lines(
    path: Path,
    *,
    include_system: bool,
    include_events: bool,
) -> list[str]:
    out: list[str] = []
    if not path.exists():
        return out

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue

            rendered = _render_event_line(
                ev,
                include_system=include_system,
                include_events=include_events,
            )
            if rendered is not None:
                out.append(rendered)

    return out


def _parse_rendered_event_line(
    line: str,
    *,
    include_system: bool,
    include_events: bool,
) -> str | None:
    try:
        ev = json.loads(line)
    except Exception:
        return None
    return _render_event_line(
        ev,
        include_system=include_system,
        include_events=include_events,
    )


def _render_log_message(msg: ChatMessage, *, ts_ms: int | None = None) -> str:
    ts_prefix = f"{COLOR_DIM}[{_format_ts(ts_ms)}]{COLOR_RESET} "

    # Determine role color
    if msg.role == "user":
        role_color = COLOR_GREEN
    elif msg.role == "assistant":
        if msg.tool_calls:
            role_color = COLOR_YELLOW
        else:
            role_color = COLOR_CYAN
    elif msg.role == "system":
        role_color = COLOR_MAGENTA
    elif msg.role == "tool":
        role_color = COLOR_BLUE
    elif msg.role == "thinking":
        role_color = COLOR_YELLOW + COLOR_DIM  # Dim yellow for thinking
    else:
        role_color = COLOR_WHITE

    # Format role label
    if msg.role == "tool":
        role_label = f"TOOL:{msg.name or 'tool'}"
    elif msg.role == "assistant" and msg.tool_calls:
        role_label = "ASSISTANT:tool_calls"
    else:
        role_label = msg.role.upper()

    colored_role = f"{role_color}[{role_label}]{COLOR_RESET}"

    content = (msg.content or "").strip()
    if not content and msg.tool_calls:
        calls = ", ".join(tc.function.name for tc in msg.tool_calls)
        content = f"(tool calls: {calls})"
    if not content:
        content = "(empty)"

    lines = content.splitlines()
    if len(lines) == 1:
        return f"{ts_prefix}{colored_role} {lines[0]}"

    first = f"{ts_prefix}{colored_role} {lines[0]}"
    rest = "\n".join(f"  {line}" for line in lines[1:])
    return f"{first}\n{rest}"




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


def _handle_slash(line: str, *, registry: ToolRegistry, transcript: Transcript, messages: list[ChatMessage]) -> bool:
    # Returns True if handled.
    if not line.startswith("/"):
        return False

    parts = line.strip().split(" ", 2)
    cmd = parts[0].lower()

    if cmd in {"/exit", "/quit"}:
        raise typer.Exit(0)

    if cmd == "/read" and len(parts) >= 2:
        try:
            out = registry.call("file_read", {"path": parts[1]})
        except Exception as e:
            out = f"Tool error: {type(e).__name__}: {e}"
        print(out)
        sys_msg = ChatMessage(role="system", content=f"/read {parts[1]}\n\n{out}")
        messages.append(sys_msg)
        transcript.append("model_message", sys_msg.model_dump(exclude_none=True))
        return True

    if cmd == "/write" and len(parts) == 3:
        path = parts[1]
        content = parts[2]
        try:
            out = registry.call("file_write", {"path": path, "content": content})
        except Exception as e:
            out = f"Tool error: {type(e).__name__}: {e}"
        print(out)
        sys_msg = ChatMessage(role="system", content=f"/write {path}\n\n{out}")
        messages.append(sys_msg)
        transcript.append("model_message", sys_msg.model_dump(exclude_none=True))
        return True

    if cmd == "/workspace" and len(parts) >= 2:
        path = parts[1]
        try:
            out = registry.call("create_workspace", {"path": path})
        except Exception as e:
            out = f"Tool error: {type(e).__name__}: {e}"
        print(out)
        sys_msg = ChatMessage(role="system", content=f"/workspace {path}\n\n{out}")
        messages.append(sys_msg)
        transcript.append("model_message", sys_msg.model_dump(exclude_none=True))
        return True

    if cmd in {"/workspace_ls", "/ws"}:
        path = parts[1] if len(parts) >= 2 else "."
        try:
            out = registry.call("workspace_list", {"path": path})
        except Exception as e:
            out = f"Tool error: {type(e).__name__}: {e}"
        print(out)
        sys_msg = ChatMessage(role="system", content=f"/workspace_ls {path}\n\n{out}")
        messages.append(sys_msg)
        transcript.append("model_message", sys_msg.model_dump(exclude_none=True))
        return True

    if cmd == "/shell" and len(parts) >= 2:
        cmdline = line.strip()[len("/shell") :].strip()
        try:
            out = registry.call("shell_run", {"command": cmdline})
        except Exception as e:
            out = f"Tool error: {type(e).__name__}: {e}"
        print(out)
        sys_msg = ChatMessage(role="system", content=f"/shell {cmdline}\n\n{out}")
        messages.append(sys_msg)
        transcript.append("model_message", sys_msg.model_dump(exclude_none=True))
        return True

    if cmd == "/help":
        print(
            "Slash commands: /read <path>, /write <path> <content>, /workspace <path>, "
            "/workspace_ls [path], /shell <cmd>, /exit"
        )
        return True

    print("Unknown command. Use /help")
    return True


@app.command()
def chat(
    prompt: str = typer.Argument(..., help="User prompt"),
    resume: str | None = typer.Option(None, "--resume", help="Resume from an existing session id"),
    workspace_root: Path | None = typer.Option(None, help="Workspace root (sandbox)"),
    show_tools: bool = typer.Option(
        False,
        "--show-tools/--no-show-tools",
        help="Print tool outputs (e.g., file_read contents) to the terminal.",
    ),
    thinking: bool = typer.Option(
        None,
        "--thinking/--no-thinking",
        help="Enable thinking/reasoning output. Overrides config setting.",
    ),
):
    settings = Settings.load(workspace_root=workspace_root)
    if workspace_root is not None:
        settings.workspace_root = workspace_root

    defaults = default_sessions(
        workspace_root=settings.workspace_root,
        transcript_dir=settings.resolved_transcript_dir(),
    )
    session_id = resume or defaults.chat
    session = open_session(transcript_dir=settings.resolved_transcript_dir(), session_id=session_id)
    transcript = Transcript(path=session.path)

    messages = load_model_messages(transcript)

    # Determine thinking setting: command line overrides config
    thinking_enabled = settings.thinking_enabled
    if thinking is not None:
        thinking_enabled = thinking

    # 使用新的ToolManager
    tool_manager = create_tool_manager(settings)
    registry = tool_manager.registry

    prompt_manager = PromptManager(settings=settings)
    system_message = prompt_manager.build_system_message(
        mode="chat",
        tool_specs=registry.specs(),
        thinking_enabled=thinking_enabled,
    )
    _ensure_message_bootstrap(messages, transcript, system_message=system_message)

    client = make_llm_client(settings)

    try:
        tool_context = tool_manager.create_tool_context(
            session_id=session_id,
            transcript=transcript,
            workspace_root=settings.workspace_root,
        )
        run_query(
            client=client,
            registry=registry,
            transcript=transcript,
            messages=messages,
            user_text=prompt,
            max_turns=settings.max_turns,
            stream_printer=_print_delta,
            tool_printer=_print_tool_output if show_tools else None,
            tool_context=tool_context,
            tool_limits=ToolLimits(
                max_tool_calls=settings.max_tool_calls,
                max_tool_calls_per_tool=settings.max_tool_calls_per_tool,
                max_tool_calls_same_args=settings.max_tool_calls_same_args,
            ),
            thinking_enabled=thinking_enabled,
        )
        print("")
        print(f"\n[session_id={session_id}] transcript={transcript.path}")
    finally:
        client.close()


@app.command()
def repl(
    resume: str | None = typer.Option(None, "--resume", help="Resume from an existing session id"),
    workspace_root: Path | None = typer.Option(None, help="Workspace root (sandbox)"),
    show_tools: bool = typer.Option(
        True,
        "--show-tools/--no-show-tools",
        help="Print tool outputs (e.g., file_read contents) to the terminal.",
    ),
    thinking: bool = typer.Option(
        None,
        "--thinking/--no-thinking",
        help="Enable thinking/reasoning output. Overrides config setting.",
    ),
):
    settings = Settings.load(workspace_root=workspace_root)
    if workspace_root is not None:
        settings.workspace_root = workspace_root

    defaults = default_sessions(
        workspace_root=settings.workspace_root,
        transcript_dir=settings.resolved_transcript_dir(),
    )
    session_id = resume or defaults.repl
    session = open_session(transcript_dir=settings.resolved_transcript_dir(), session_id=session_id)
    transcript = Transcript(path=session.path)

    messages = load_model_messages(transcript)

    # Determine thinking setting: command line overrides config
    thinking_enabled = settings.thinking_enabled
    if thinking is not None:
        thinking_enabled = thinking

    # 使用新的ToolManager
    tool_manager = create_tool_manager(settings)
    registry = tool_manager.registry

    prompt_manager = PromptManager(settings=settings)
    system_message = prompt_manager.build_system_message(
        mode="repl",
        tool_specs=registry.specs(),
        thinking_enabled=thinking_enabled,
    )
    _ensure_message_bootstrap(messages, transcript, system_message=system_message)

    client = make_llm_client(settings)

    print(f"GGbot REPL  session_id={session_id}")
    print("Type /help for commands. Ctrl+C to exit.")

    try:
        tool_context = tool_manager.create_tool_context(
            session_id=session_id,
            transcript=transcript,
            workspace_root=settings.workspace_root,
        )
        while True:
            try:
                line = input("> ")
            except (EOFError, KeyboardInterrupt):
                print("")
                break

            line = line.rstrip("\n")
            if not line.strip():
                continue

            if line.startswith("/"):
                _handle_slash(line, registry=registry, transcript=transcript, messages=messages)
                continue

            run_query(
                client=client,
                registry=registry,
                transcript=transcript,
                messages=messages,
                user_text=line,
                max_turns=settings.max_turns,
                stream_printer=_print_delta,
                tool_printer=_print_tool_output if show_tools else None,
                tool_context=tool_context,
                tool_limits=ToolLimits(
                    max_tool_calls=settings.max_tool_calls,
                    max_tool_calls_per_tool=settings.max_tool_calls_per_tool,
                    max_tool_calls_same_args=settings.max_tool_calls_same_args,
                ),
                thinking_enabled=thinking_enabled,
            )
            print("")

    finally:
        client.close()
        print(f"[session_id={session_id}] transcript={transcript.path}")


@app.command()
def tui(
    resume: str | None = typer.Option(None, "--resume", help="Resume from an existing session id"),
    workspace_root: Path | None = typer.Option(None, help="Workspace root (sandbox)"),
):
    """Full-screen terminal UI (Textual)."""

    from .ui.tui import run_tui

    run_tui(resume=resume, workspace_root=workspace_root)


@app.command("log")
def log_view(
    session: str | None = typer.Option(None, "--session", help="Session id to inspect."),
    workspace_root: Path | None = typer.Option(None, help="Workspace root (sandbox)."),
    tail: int = typer.Option(200, "--tail", min=1, max=5000, help="Show only the last N messages."),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow transcript in real time."),
    poll_ms: int = typer.Option(400, "--poll-ms", min=100, max=5000, help="Polling interval in follow mode."),
    include_events: bool = typer.Option(
        True,
        "--events/--no-events",
        help="Include runtime events such as tool_call/tool_result.",
    ),
    include_system: bool = typer.Option(
        False,
        "--include-system/--no-include-system",
        help="Include system messages in log output.",
    ),
) -> None:
    """Show transcript log in a dedicated terminal view."""

    settings = Settings.load(workspace_root=workspace_root)
    if workspace_root is not None:
        settings.workspace_root = workspace_root

    transcript_dir = settings.resolved_transcript_dir()
    defaults = default_sessions(
        workspace_root=settings.workspace_root,
        transcript_dir=transcript_dir,
    )

    session_id = session or _most_recent_session_id(transcript_dir) or defaults.repl
    session_info = open_session(transcript_dir=transcript_dir, session_id=session_id)
    path = session_info.path

    if not path.exists():
        print(f"No transcript found for session_id={session_id}")
        print(f"transcript_dir={transcript_dir}")
        return

    lines = _iter_rendered_log_lines(
        path,
        include_system=include_system,
        include_events=include_events,
    )

    if not lines:
        print(f"Transcript is empty for session_id={session_id}")
        print(f"transcript={path}")
        if not follow:
            return

    shown = lines[-tail:]
    print(
        f"GGbot log  session_id={session_id}  total={len(lines)}  showing={len(shown)}"
    )
    print(f"transcript={path}")
    print("-" * 72)
    for item in shown:
        print(item)

    if not follow:
        return

    print("-" * 72)
    print("Following... Press Ctrl+C to stop.")
    sleep_s = poll_ms / 1000.0

    with path.open("r", encoding="utf-8") as f:
        f.seek(0, 2)
        try:
            while True:
                line = f.readline()
                if not line:
                    time.sleep(sleep_s)
                    continue

                rendered = _parse_rendered_event_line(
                    line,
                    include_system=include_system,
                    include_events=include_events,
                )
                if rendered is None:
                    continue
                print(rendered)
        except KeyboardInterrupt:
            print("\nStopped following.")


@app.command("log-enhanced")
def log_enhanced(
    session: str | None = typer.Option(None, "--session", help="Session id to inspect."),
    workspace_root: Path | None = typer.Option(None, help="Workspace root (sandbox)."),
    html: bool = typer.Option(False, "--html", help="Export to HTML format."),
    output: Path = typer.Option(Path("ggbot_log.html"), "--output", help="Output file for HTML export."),
    include_roles: str = typer.Option("", "--include-roles", help="Comma-separated roles to include (system,user,assistant,tool,thinking)."),
    exclude_roles: str = typer.Option("", "--exclude-roles", help="Comma-separated roles to exclude."),
    include_types: str = typer.Option("", "--include-types", help="Comma-separated event types to include."),
    exclude_types: str = typer.Option("", "--exclude-types", help="Comma-separated event types to exclude."),
    search: str = typer.Option("", "--search", help="Search text in content."),
    min_length: int = typer.Option(0, "--min-length", help="Minimum content length."),
    max_length: int = typer.Option(0, "--max-length", help="Maximum content length (0=unlimited)."),
    show_raw: bool = typer.Option(False, "--show-raw", help="Show raw model content."),
    stats: bool = typer.Option(False, "--stats", help="Show statistics only."),
) -> None:
    """Enhanced log viewer with filtering and HTML export."""
    try:
        from ggbot.core.log_enhancer import LogEnhancer, LogFilter
    except ImportError:
        typer.echo("Error: log_enhancer module not found. Make sure it's installed.")
        return

    settings = Settings.load(workspace_root=workspace_root)
    if workspace_root is not None:
        settings.workspace_root = workspace_root

    transcript_dir = settings.resolved_transcript_dir()
    defaults = default_sessions(
        workspace_root=settings.workspace_root,
        transcript_dir=transcript_dir,
    )

    session_id = session or _most_recent_session_id(transcript_dir) or defaults.repl
    session_info = open_session(transcript_dir=transcript_dir, session_id=session_id)
    path = session_info.path

    if not path.exists():
        typer.echo(f"No transcript found for session_id={session_id}")
        typer.echo(f"transcript_dir={transcript_dir}")
        return

    # 创建日志增强器
    enhancer = LogEnhancer(path)

    # 创建筛选器
    filter_obj = LogFilter(
        include_roles=set(include_roles.split(",")) if include_roles else set(),
        exclude_roles=set(exclude_roles.split(",")) if exclude_roles else set(),
        include_types=set(include_types.split(",")) if include_types else set(),
        exclude_types=set(exclude_types.split(",")) if exclude_types else set(),
        min_length=min_length,
        max_length=max_length if max_length > 0 else 0,
        search_text=search,
    )

    # 显示统计信息
    if stats:
        stats_data = enhancer.get_statistics()
        typer.echo(f"Session: {session_id}")
        typer.echo(f"Total events: {stats_data['total_events']}")

        if stats_data['by_type']:
            typer.echo("\nEvents by type:")
            for event_type, count in sorted(stats_data['by_type'].items()):
                typer.echo(f"  {event_type}: {count}")

        if stats_data['by_role']:
            typer.echo("\nEvents by role:")
            for role, count in sorted(stats_data['by_role'].items()):
                typer.echo(f"  {role}: {count}")

        if stats_data['time_range']:
            tr = stats_data['time_range']
            start_dt = datetime.fromtimestamp(tr['start'] / 1000)
            end_dt = datetime.fromtimestamp(tr['end'] / 1000)
            duration_sec = tr['duration_ms'] / 1000
            typer.echo(f"\nTime range: {start_dt} to {end_dt}")
            typer.echo(f"Duration: {duration_sec:.1f} seconds")

        if stats_data['content_stats']:
            cs = stats_data['content_stats']
            typer.echo(f"\nContent statistics:")
            typer.echo(f"  Total characters: {cs['total_chars']:,}")
            typer.echo(f"  Average per event: {cs['avg_chars_per_event']:,}")

        return

    # HTML导出
    if html:
        typer.echo(f"Exporting to HTML: {output}")
        enhancer.export_to_html(filter_obj, output)
        typer.echo(f"HTML export completed: {output}")
        return

    # 控制台显示
    filtered_events = enhancer.filter_events(filter_obj)

    if not filtered_events:
        typer.echo("No events match the filter criteria.")
        return

    typer.echo(f"GGbot Enhanced Log - Session: {session_id}")
    typer.echo(f"Total events: {len(enhancer.events)}, Filtered: {len(filtered_events)}")
    typer.echo(f"Transcript: {path}")
    typer.echo("-" * 80)

    for event in filtered_events:
        # 格式化时间戳
        dt = datetime.fromtimestamp(event.ts_ms / 1000)
        time_str = dt.strftime("%H:%M:%S")

        # 角色和类型
        role_display = event.role or event.event_type
        if event.name:
            role_display = f"{role_display}:{event.name}"

        # 颜色编码
        color = COLOR_WHITE
        if event.role == "system":
            color = COLOR_MAGENTA
        elif event.role == "user":
            color = COLOR_GREEN
        elif event.role == "assistant":
            color = COLOR_YELLOW
        elif event.role == "tool":
            color = COLOR_BLUE
        elif event.role == "thinking":
            color = COLOR_YELLOW + COLOR_DIM

        # 显示事件
        typer.echo(f"{COLOR_DIM}[{time_str}]{COLOR_RESET} {color}{role_display}{COLOR_RESET}")

        if event.content:
            # 显示内容（截断长内容）
            content_preview = event.content
            if len(content_preview) > 500:
                content_preview = content_preview[:497] + "..."
            # 处理编码问题
            try:
                typer.echo(f"  {content_preview}")
            except UnicodeEncodeError:
                # 如果遇到编码问题，尝试使用安全的编码
                safe_preview = content_preview.encode('utf-8', errors='replace').decode('utf-8')
                typer.echo(f"  {safe_preview}")

        if show_raw and event.raw_content:
            typer.echo(f"  {COLOR_DIM}Raw:{COLOR_RESET}")
            raw_preview = event.raw_content
            if len(raw_preview) > 300:
                raw_preview = raw_preview[:297] + "..."
            typer.echo(f"    {raw_preview}")

        if event.tool_calls:
            typer.echo(f"  {COLOR_DIM}Tool calls:{COLOR_RESET}")
            for tool_call in event.tool_calls:
                func = tool_call.get("function", {})
                typer.echo(f"    {func.get('name', 'unknown')}({func.get('arguments', '')})")

        typer.echo()  # 空行分隔


@app.command("log-raw")
def log_raw_content(
    session: str | None = typer.Option(None, "--session", help="Session id to inspect."),
    workspace_root: Path | None = typer.Option(None, help="Workspace root (sandbox)."),
) -> None:
    """Show raw model content for debugging."""
    try:
        from ggbot.core.log_enhancer import LogEnhancer
    except ImportError:
        typer.echo("Error: log_enhancer module not found. Make sure it's installed.")
        return

    settings = Settings.load(workspace_root=workspace_root)
    if workspace_root is not None:
        settings.workspace_root = workspace_root

    transcript_dir = settings.resolved_transcript_dir()
    defaults = default_sessions(
        workspace_root=settings.workspace_root,
        transcript_dir=transcript_dir,
    )

    session_id = session or _most_recent_session_id(transcript_dir) or defaults.repl
    session_info = open_session(transcript_dir=transcript_dir, session_id=session_id)
    path = session_info.path

    if not path.exists():
        typer.echo(f"No transcript found for session_id={session_id}")
        return

    enhancer = LogEnhancer(path)
    raw_contents = enhancer.extract_model_raw_content()

    if not raw_contents:
        typer.echo("No raw model content found.")
        return

    typer.echo(f"Raw Model Content - Session: {session_id}")
    typer.echo(f"Found {len(raw_contents)} model messages with raw content")
    typer.echo("-" * 80)

    for i, content in enumerate(raw_contents, 1):
        dt = datetime.fromtimestamp(content['ts_ms'] / 1000)
        time_str = dt.strftime("%H:%M:%S")

        typer.echo(f"{i}. [{time_str}] {content['role']}")
        typer.echo(f"   Raw content ({len(content['raw_content'])} chars):")
        typer.echo(f"   {COLOR_DIM}{content['raw_content']}{COLOR_RESET}")

        if content['parsed_content'] and content['parsed_content'] != content['raw_content']:
            typer.echo(f"   Parsed content ({len(content['parsed_content'])} chars):")
            typer.echo(f"   {content['parsed_content']}")

        if content['tool_calls']:
            typer.echo(f"   Tool calls: {len(content['tool_calls'])}")

        typer.echo()
