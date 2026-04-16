from __future__ import annotations

from typing import Any, Callable, Protocol

from ..domain.types import AssistantFinal, ChatMessage


class ProviderError(Exception):
    """Raised when the underlying LLM provider call fails."""


class ChatCompletionClient(Protocol):
    def stream_and_collect(
        self,
        *,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None,
        on_text_delta: Callable[[str], None] | None = None,
    ) -> AssistantFinal: ...

    def complete(self, *, messages: list[ChatMessage], tools: list[dict[str, Any]] | None) -> AssistantFinal: ...

    def close(self) -> None: ...
