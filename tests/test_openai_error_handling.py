import httpx
import pytest

from ggbot.core.types import ChatMessage
from ggbot.core.query_loop import run_query
from ggbot.core.transcript import Transcript
from ggbot.providers.openai_client import OpenAIClientError, OpenAICompatibleClient
from ggbot.tools.registry import ToolRegistry


def test_streaming_http_error_does_not_raise_response_not_read() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            headers={"content-type": "application/json"},
            content=b'{"error":"unauthorized"}',
        )

    client = OpenAICompatibleClient(
        base_url="https://example.test/v1",
        api_key=None,
        model="test-model",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(OpenAIClientError) as e:
        list(client.stream_chat_completions(messages=[ChatMessage(role="user", content="hi")], tools=None))

    assert "HTTP 401" in str(e.value)
    assert "unauthorized" in str(e.value)

    client.close()


def test_run_query_turns_provider_http_error_into_system_message(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            headers={"content-type": "application/json"},
            content=b'{"error":"unauthorized"}',
        )

    client = OpenAICompatibleClient(
        base_url="https://example.test/v1",
        api_key=None,
        model="test-model",
        transport=httpx.MockTransport(handler),
    )

    reg = ToolRegistry()
    transcript = Transcript(path=tmp_path / "t.jsonl")
    messages: list[ChatMessage] = [ChatMessage(role="system", content="sys")]

    # Should not raise.
    run_query(
        client=client,
        registry=reg,
        transcript=transcript,
        messages=messages,
        user_text="hi",
        max_turns=1,
        stream_printer=None,
    )

    # A system message describing the provider error should be appended.
    assert any(m.role == "system" and "HTTP 401" in m.content for m in messages)

    client.close()
