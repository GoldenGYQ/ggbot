from __future__ import annotations

import sys
from pathlib import Path

import typer

from ggbot.core.config import Settings
from ggbot.core.sessions import default_sessions
from ggbot.core.query_loop import run_query
from ggbot.providers.openai_client import OpenAICompatibleClient
from ggbot.tools.file_tools import make_file_tools
from ggbot.tools.jobs_tool import make_job_tools
from ggbot.tools.registry import ToolRegistry
from ggbot.tools.shell_tool import make_shell_tool
from ggbot.tools.workspace_tools import make_workspace_tools
from ggbot.core.transcript import Transcript, load_model_messages, open_session
from ggbot.core.types import ChatMessage

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


def _register_builtin_tools(registry: ToolRegistry, settings: Settings, *, shell_confirm_callback=None) -> None:
    file_read, file_write = make_file_tools(workspace_root=settings.workspace_root)
    create_workspace, workspace_list = make_workspace_tools(workspace_root=settings.workspace_root)
    shell_run = make_shell_tool(
        workspace_root=settings.workspace_root,
        confirm=settings.shell_confirm,
        timeout_ms=settings.shell_timeout_ms,
        max_output_chars=settings.shell_max_output_chars,
        confirm_callback=shell_confirm_callback,
    )
    shell_jobs, shell_tail, shell_kill = make_job_tools(workspace_root=settings.workspace_root)

    for fn in (file_read, file_write, create_workspace, workspace_list, shell_run, shell_jobs, shell_tail, shell_kill):
        reg = getattr(fn, "__ggbot_tool__")
        registry.register(reg.spec, reg.handler)


def _ensure_message_bootstrap(messages: list[ChatMessage], transcript: Transcript) -> None:
    if messages and messages[0].role == "system":
        return
    msg = _default_system_message()
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
):
    settings = Settings.load(workspace_root=workspace_root)
    if workspace_root is not None:
        settings.workspace_root = workspace_root

    if not settings.openai_api_key:
        raise typer.BadParameter(
            "Missing OPENAI_API_KEY. Set it via env, .env, or .ggbot/config.toml (see python-mvp/README.md)."
        )

    defaults = default_sessions(
        workspace_root=settings.workspace_root,
        transcript_dir=settings.resolved_transcript_dir(),
    )
    session_id = resume or defaults.chat
    session = open_session(transcript_dir=settings.resolved_transcript_dir(), session_id=session_id)
    transcript = Transcript(path=session.path)

    messages = load_model_messages(transcript)

    _ensure_message_bootstrap(messages, transcript)

    registry = ToolRegistry()
    _register_builtin_tools(registry, settings)

    client = OpenAICompatibleClient(
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
        model=settings.openai_model,
    )

    try:
        run_query(
            client=client,
            registry=registry,
            transcript=transcript,
            messages=messages,
            user_text=prompt,
            max_turns=settings.max_turns,
            stream_printer=_print_delta,
            tool_printer=_print_tool_output if show_tools else None,
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
):
    settings = Settings.load(workspace_root=workspace_root)
    if workspace_root is not None:
        settings.workspace_root = workspace_root

    if not settings.openai_api_key:
        raise typer.BadParameter(
            "Missing OPENAI_API_KEY. Set it via env, .env, or .ggbot/config.toml (see python-mvp/README.md)."
        )

    defaults = default_sessions(
        workspace_root=settings.workspace_root,
        transcript_dir=settings.resolved_transcript_dir(),
    )
    session_id = resume or defaults.repl
    session = open_session(transcript_dir=settings.resolved_transcript_dir(), session_id=session_id)
    transcript = Transcript(path=session.path)

    messages = load_model_messages(transcript)
    _ensure_message_bootstrap(messages, transcript)

    registry = ToolRegistry()
    _register_builtin_tools(registry, settings)

    client = OpenAICompatibleClient(
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
        model=settings.openai_model,
    )

    print(f"GGbot REPL  session_id={session_id}")
    print("Type /help for commands. Ctrl+C to exit.")

    try:
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
