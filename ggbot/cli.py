from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List

import typer

from ggbot.core.agent_loop import ToolLimits, run_query
from ggbot.core.runtime import create_agent_bootstrap, create_app_session
from ggbot.core.runtime_events import consume_runtime_events
from ggbot.tools.context import ToolContext
from ggbot.tools.registry import ToolRegistry
from ggbot.core.transcript import Transcript
from ggbot.core.types import ChatMessage
# 事件监听器导入
try:
    from ggbot.cli_tools.event_monitor import (
        EventFilter,
        OutputFormat,
        run_interactive_monitor,
        run_simple_monitor,
        create_event_filter_from_args
    )
    EVENT_MONITOR_AVAILABLE = True
except ImportError:
    EVENT_MONITOR_AVAILABLE = False

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

    # 清理内容中的换行符，确保单行显示
    content = content.replace('\n', ' ').replace('\r', '')

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
    app_session = create_app_session(
        workspace_root=workspace_root,
        resume=resume,
        default_session_name="chat",
    )
    settings = app_session.settings
    session_id = app_session.session_id
    transcript = app_session.transcript

    # Determine thinking setting: command line overrides config
    thinking_enabled = settings.thinking_enabled
    if thinking is not None:
        thinking_enabled = thinking

    bootstrap = create_agent_bootstrap(
        settings=settings,
        session_id=session_id,
        transcript=transcript,
        mode="chat",
        thinking_enabled=thinking_enabled,
    )
    runtime = bootstrap.runtime

    try:
        tool_context = bootstrap.tool_manager.create_tool_context(
            session_id=session_id,
            transcript=transcript,
            workspace_root=settings.workspace_root,
        )
        result = run_query(
            client=runtime.client,
            registry=runtime.registry,
            transcript=runtime.transcript,
            messages=runtime.messages,
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
        consume_runtime_events(
            result.events,
            on_provider_error=lambda data: print(f"provider_error: {data.get('error', 'unknown')}"),
        )
        print("")
        print(f"\n[session_id={session_id}] transcript={transcript.path}")
    finally:
        bootstrap.client.close()


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
    app_session = create_app_session(
        workspace_root=workspace_root,
        resume=resume,
        default_session_name="repl",
    )
    settings = app_session.settings
    session_id = app_session.session_id
    transcript = app_session.transcript

    # Determine thinking setting: command line overrides config
    thinking_enabled = settings.thinking_enabled
    if thinking is not None:
        thinking_enabled = thinking

    bootstrap = create_agent_bootstrap(
        settings=settings,
        session_id=session_id,
        transcript=transcript,
        mode="repl",
        thinking_enabled=thinking_enabled,
    )
    runtime = bootstrap.runtime

    print(f"GGbot REPL  session_id={session_id}")
    print("Type /help for commands. Ctrl+C to exit.")

    try:
        tool_context = bootstrap.tool_manager.create_tool_context(
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
                _handle_slash(line, registry=runtime.registry, transcript=runtime.transcript, messages=runtime.messages)
                continue

            result = run_query(
                client=runtime.client,
                registry=runtime.registry,
                transcript=runtime.transcript,
                messages=runtime.messages,
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
            consume_runtime_events(
                result.events,
                on_provider_error=lambda data: print(f"provider_error: {data.get('error', 'unknown')}"),
            )
            print("")

    finally:
        bootstrap.client.close()
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

    app_session = create_app_session(
        workspace_root=workspace_root,
        resume=session,
        default_session_name="repl",
        prefer_recent=True,
    )
    settings = app_session.settings
    session_id = app_session.session_id
    transcript_dir = settings.resolved_transcript_dir()
    path = app_session.transcript.path

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


@app.command("events")
def event_monitor(
    interactive: bool = typer.Option(
        False,
        "--interactive", "-i",
        help="使用交互式界面（Rich TUI）"
    ),
    format: str = typer.Option(
        "text",
        "--format", "-f",
        help="输出格式：text, json, rich, table",
        case_sensitive=False
    ),
    types: Optional[List[str]] = typer.Option(
        None,
        "--type", "-t",
        help="过滤事件类型（可多次指定）"
    ),
    source: Optional[str] = typer.Option(
        None,
        "--source", "-s",
        help="过滤事件来源（包含匹配）"
    ),
    contains: Optional[str] = typer.Option(
        None,
        "--contains", "-c",
        help="过滤事件数据内容（包含匹配）"
    ),
    severity: Optional[str] = typer.Option(
        None,
        "--severity",
        help="最小严重级别：debug, info, warning, error, critical"
    ),
    duration: Optional[float] = typer.Option(
        None,
        "--duration", "-d",
        help="运行时长（秒），默认持续运行"
    ),
) -> None:
    """实时监听运行时事件"""

    if not EVENT_MONITOR_AVAILABLE:
        print("错误：事件监听器模块不可用")
        print("请确保 ggbot.cli.event_monitor 模块已正确安装")
        return

    # 验证输出格式
    try:
        output_format = OutputFormat(format.lower())
    except ValueError:
        print(f"错误：无效的输出格式 '{format}'")
        print("可用格式：text, json, rich, table")
        return

    # 创建事件过滤器
    event_filter = create_event_filter_from_args(
        event_types=types,
        source=source,
        contains=contains,
        min_severity=severity
    )

    if interactive:
        # 交互式模式
        if output_format != OutputFormat.RICH:
            print("注意：交互式模式强制使用 rich 格式")

        try:
            run_interactive_monitor(event_filter, OutputFormat.RICH)
        except KeyboardInterrupt:
            print("\n已退出交互式模式")
        except Exception as e:
            print(f"错误：{e}")
    else:
        # 简单模式（单进程）
        try:
            run_simple_monitor(event_filter, output_format, duration)
        except KeyboardInterrupt:
            print("\n已停止监听")
        except Exception as e:
            print(f"错误：{e}")
