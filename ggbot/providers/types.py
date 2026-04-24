from __future__ import annotations

from typing import Any, Callable, Protocol

from ..models.protocol_models import AssistantFinal, ChatMessage


class ProviderError(Exception):
    """Raised when the underlying LLM provider call fails."""


class GenerationInterrupted(Exception):
    """Raised when generation is intentionally interrupted by runtime control."""


class ChatCompletionClient(Protocol):
    def stream_and_collect(
        self,
        *,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None,
        on_text_delta: Callable[[str], None] | None = None,
        on_raw_chunk: Callable[[dict[str, Any]], None] | None = None,
        interrupt_callback: Callable[[], bool] | None = None,
    ) -> AssistantFinal: ...

    def complete(self, *, messages: list[ChatMessage], tools: list[dict[str, Any]] | None) -> AssistantFinal: ...

    def close(self) -> None: ...
