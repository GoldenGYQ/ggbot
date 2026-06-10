"""Tests for graceful handling of provider (LLM) errors in the agent loop."""

from __future__ import annotations

import pytest

from ggbot.runtime.agent_loop import run_query
from ggbot.state.transcript import Transcript
from ggbot.models.protocol_models import AssistantFinal, ChatMessage
from ggbot.providers.types import ProviderError
from ggbot.tools.registry import ToolRegistry


class _FailingClient:
    def close(self) -> None:
        return

    def complete(self, *, messages: list[ChatMessage], tools):
        return self.stream_and_collect(messages=messages, tools=tools, on_text_delta=None)

    def stream_and_collect(self, *, messages: list[ChatMessage], tools, on_text_delta=None) -> AssistantFinal:
        raise ProviderError("HTTP 401: unauthorized")


@pytest.mark.unit
def test_run_query_turns_provider_error_into_system_message(tmp_path: Path) -> None:
    """A ProviderError from the LLM should be converted to a system message, not crash the loop."""
    reg = ToolRegistry()
    transcript = Transcript(path=tmp_path / "t.jsonl")
    messages: list[ChatMessage] = [ChatMessage(role="system", content="sys")]

    run_query(
        client=_FailingClient(),
        registry=reg,
        transcript=transcript,
        messages=messages,
        user_text="hi",
        max_turns=1,
        stream_printer=None,
    )

    assert any(m.role == "system" and "HTTP 401" in m.content for m in messages)

