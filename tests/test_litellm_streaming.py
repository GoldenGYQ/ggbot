from __future__ import annotations

from typing import Any, Iterable

import litellm
import pytest

from ggbot.models.protocol_models import ChatMessage
from ggbot.providers.litellm_client import LiteLLMClient


def test_litellm_stream_and_collect_merges_content_and_tool_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    chunks: list[dict[str, Any]] = [
        {"choices": [{"delta": {"content": "Hel"}}]},
        {"choices": [{"delta": {"content": "lo"}}]},
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_1",
                                "function": {"name": "file_read", "arguments": "{\"path\":\"foo"},
                            }
                        ]
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {"index": 0, "function": {"arguments": ".txt\"}"}}
                        ]
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        },
    ]

    def fake_completion(*args: Any, **kwargs: Any) -> Iterable[dict[str, Any]]:
        assert kwargs.get("stream") is True
        return iter(chunks)

    monkeypatch.setattr(litellm, "completion", fake_completion)

    client = LiteLLMClient(model="test-model", api_base="https://example.test/v1", api_key="test")

    deltas: list[str] = []
    final = client.stream_and_collect(
        messages=[ChatMessage(role="user", content="hi")],
        tools=None,
        on_text_delta=deltas.append,
    )

    assert "".join(deltas) == "Hello"
    assert final.content == "Hello"
    assert len(final.tool_calls) == 1
    assert final.tool_calls[0].id == "call_1"
    assert final.tool_calls[0].function.name == "file_read"
    assert final.tool_calls[0].function.arguments == '{"path":"foo.txt"}'
