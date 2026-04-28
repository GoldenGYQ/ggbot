from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ..app.app_bootstrap import AgentRuntime, ensure_message_bootstrap
from ..models.protocol_models import ChatMessage
from ..runtime.history_repair import auto_heal_missing_tool_messages, sanitize_orphan_tool_messages
from ..state.transcript import Transcript, load_model_messages, open_session


@dataclass
class SessionExecutionContext:
    session_id: str
    transcript: Transcript
    messages: list[ChatMessage]


class SessionRuntimeManager:
    """Manage per-session execution contexts for API mode."""

    def __init__(self, runtime: AgentRuntime):
        self._runtime = runtime
        self._current_session_id = runtime.session_id
        self._session_contexts: dict[str, SessionExecutionContext] = {}
        self._session_locks: dict[str, asyncio.Lock] = {
            runtime.session_id: asyncio.Lock()
        }

        runtime_transcript = getattr(runtime, "transcript", None)
        runtime_messages = getattr(runtime, "messages", None)
        if isinstance(runtime_transcript, Transcript) and isinstance(runtime_messages, list):
            self._session_contexts[runtime.session_id] = SessionExecutionContext(
                session_id=runtime.session_id,
                transcript=runtime_transcript,
                messages=runtime_messages,
            )

    @property
    def current_session_id(self) -> str:
        return self._current_session_id

    @current_session_id.setter
    def current_session_id(self, value: str) -> None:
        self._current_session_id = value

    def get_lock(self, session_id: str) -> asyncio.Lock:
        lock = self._session_locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._session_locks[session_id] = lock
        return lock

    def get_or_create_context(self, session_id: str) -> SessionExecutionContext:
        context = self._session_contexts.get(session_id)
        if context is not None:
            return context

        session = open_session(
            transcript_dir=self._runtime.settings.resolved_transcript_dir(),
            session_id=session_id,
        )
        transcript = Transcript(path=session.path)
        messages = load_model_messages(transcript)
        ensure_message_bootstrap(
            messages,
            transcript,
            system_message=self._runtime.system_message,
        )
        # Repair legacy/out-of-order tool traces loaded from transcript so
        # provider payload is valid before the next run starts.
        sanitize_orphan_tool_messages(messages=messages)
        auto_heal_missing_tool_messages(messages=messages)
        context = SessionExecutionContext(
            session_id=session_id,
            transcript=transcript,
            messages=messages,
        )
        self._session_contexts[session_id] = context
        self.get_lock(session_id)
        return context

    def drop_context(self, session_id: str) -> None:
        self._session_contexts.pop(session_id, None)
        self._session_locks.pop(session_id, None)
