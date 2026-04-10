import json
from typing import Iterable

import httpx

from ggbot.providers.openai_client import OpenAICompatibleClient
from ggbot.core.types import ChatMessage


def _sse_bytes(events: list[dict] | list[str]) -> Iterable[bytes]:
    for ev in events:
        if isinstance(ev, str):
            data = ev
        else:
            data = json.dumps(ev)
        yield f"data: {data}\n\n".encode("utf-8")


def test_stream_and_collect_merges_content_and_tool_calls() -> None:
    events = [
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
                    }
                }
            ]
        },
        "[DONE]",
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"".join(_sse_bytes(events)),
        )

    transport = httpx.MockTransport(handler)
    client = OpenAICompatibleClient(
        base_url="https://example.test/v1",
        api_key="test",
        model="test-model",
        transport=transport,
    )

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

    client.close()
