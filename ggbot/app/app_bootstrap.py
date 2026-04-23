from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .config import Settings
from ..prompts import PromptManager
from ..prompts.types import PromptMode
from ..state.sessions import DefaultSessions, default_sessions
from ..tools.manager import ShellConfirmCallback, ToolManager, create_tool_manager
from .client_factory import make_llm_client
from ..providers.types import ChatCompletionClient
from ..tools.registry import ToolRegistry
from ..transport.transcript_contract import transcript_event
from ..state.transcript import Transcript, clear_transcript, load_model_messages, open_session
from ..models.protocol_models import ChatMessage


@dataclass
class AgentRuntime:
    settings: Settings
    session_id: str
    transcript: Transcript
    messages: list[ChatMessage]
    system_message: ChatMessage
    registry: ToolRegistry
    client: ChatCompletionClient


@dataclass(frozen=True)
class AgentBootstrap:
    runtime: AgentRuntime
    tool_manager: ToolManager
    client: ChatCompletionClient


@dataclass(frozen=True)
class AppSession:
    settings: Settings
    defaults: DefaultSessions
    session_id: str
    transcript: Transcript


def ensure_message_bootstrap(
    messages: list[ChatMessage],
    transcript: Transcript,
    *,
    system_message: ChatMessage,
) -> None:
    if messages and messages[0].role == "system":
        return
    messages.insert(0, system_message)
    transcript.append_event(transcript_event("model_message", system_message.model_dump(exclude_none=True)))


def _most_recent_session_id(transcript_dir: Path) -> str | None:
    candidates = list(transcript_dir.glob("*.jsonl"))
    if not candidates:
        return None
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0].stem


def create_app_session(
    *,
    workspace_root: Path | None,
    resume: str | None,
    default_session_name: Literal["chat", "repl", "tui"],
    prefer_recent: bool = False,
) -> AppSession:
    settings = Settings.load(workspace_root=workspace_root)
    if workspace_root is not None:
        settings.workspace_root = workspace_root

    transcript_dir = settings.resolved_transcript_dir()
    defaults = default_sessions(workspace_root=settings.workspace_root, transcript_dir=transcript_dir)

    if resume is not None:
        session_id = resume
    elif prefer_recent:
        session_id = _most_recent_session_id(transcript_dir) or getattr(defaults, default_session_name)
    else:
        session_id = getattr(defaults, default_session_name)

    session = open_session(transcript_dir=transcript_dir, session_id=session_id)

    return AppSession(
        settings=settings,
        defaults=defaults,
        session_id=session_id,
        transcript=Transcript(path=session.path),
    )


def create_agent_runtime(
    *,
    settings: Settings,
    session_id: str,
    transcript: Transcript,
    system_message: ChatMessage,
    registry: ToolRegistry,
    client: ChatCompletionClient,
) -> AgentRuntime:
    messages = load_model_messages(transcript)
    ensure_message_bootstrap(messages, transcript, system_message=system_message)

    return AgentRuntime(
        settings=settings,
        session_id=session_id,
        transcript=transcript,
        messages=messages,
        system_message=system_message,
        registry=registry,
        client=client,
    )


def create_agent_bootstrap(
    *,
    settings: Settings,
    session_id: str,
    transcript: Transcript,
    mode: PromptMode,
    thinking_enabled: bool | None = None,
    shell_confirm_callback: ShellConfirmCallback | None = None,
) -> AgentBootstrap:
    resolved_thinking_enabled = settings.thinking_enabled if thinking_enabled is None else thinking_enabled
    tool_manager = create_tool_manager(settings, shell_confirm_callback=shell_confirm_callback)
    prompt_manager = PromptManager(settings=settings)
    system_message = prompt_manager.build_system_message(
        mode=mode,
        tool_specs=tool_manager.registry.specs(),
        thinking_enabled=resolved_thinking_enabled,
    )
    client = make_llm_client(settings)
    runtime = create_agent_runtime(
        settings=settings,
        session_id=session_id,
        transcript=transcript,
        system_message=system_message,
        registry=tool_manager.registry,
        client=client,
    )
    return AgentBootstrap(runtime=runtime, tool_manager=tool_manager, client=client)


def switch_runtime_session(
    runtime: AgentRuntime,
    *,
    session_id: str,
) -> int:
    session = open_session(transcript_dir=runtime.settings.resolved_transcript_dir(), session_id=session_id)
    transcript = Transcript(path=session.path)
    messages = load_model_messages(transcript)
    ensure_message_bootstrap(messages, transcript, system_message=runtime.system_message)

    runtime.session_id = session_id
    runtime.transcript = transcript
    runtime.messages = messages
    return len(messages)


def reset_runtime_history(runtime: AgentRuntime) -> None:
    clear_transcript(runtime.transcript)
    runtime.messages = []
    ensure_message_bootstrap(
        runtime.messages,
        runtime.transcript,
        system_message=runtime.system_message,
    )
