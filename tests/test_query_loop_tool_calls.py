import json
from pathlib import Path
from typing import Iterable

import httpx

from ggbot.providers.openai_client import OpenAICompatibleClient
from ggbot.core.query_loop import run_query
from ggbot.tools.registry import ToolRegistry, tool
from ggbot.core.transcript import Transcript
from ggbot.core.types import ChatMessage, ToolCall, ToolFunction


def _sse_bytes(events: list[dict] | list[str]) -> Iterable[bytes]:
    for ev in events:
        if isinstance(ev, str):
            data = ev
        else:
            data = json.dumps(ev)
        yield f"data: {data}\n\n".encode("utf-8")


def test_query_loop_executes_tool_calls(tmp_path: Path) -> None:
    # Model streams a tool_call, no assistant text.
    events = [
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_1",
                                "function": {"name": "echo", "arguments": "{\"text\":\"hi\"}"},
                            }
                        ]
                    }
                }
            ]
        },
        "[DONE]",
    ]

    def handler(request: httpx.Request) -> httpx.Response:
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

    from pydantic import BaseModel

    class EchoArgs(BaseModel):
        text: str

    @tool(name="echo", description="echo", input_model=EchoArgs)
    def echo(args: EchoArgs) -> str:
        return args.text

    reg = ToolRegistry()
    reg_tool = getattr(echo, "__ggbot_tool__")
    reg.register(reg_tool.spec, reg_tool.handler)

    transcript = Transcript(path=tmp_path / "t.jsonl")
    messages: list[ChatMessage] = [ChatMessage(role="system", content="sys")]

    run_query(
        client=client,
        registry=reg,
        transcript=transcript,
        messages=messages,
        user_text="do tool",
        max_turns=2,
        stream_printer=None,
    )

    # Expect tool result message appended
    tool_msgs = [m for m in messages if m.role == "tool"]
    assert tool_msgs and tool_msgs[0].content == "hi"
    assert tool_msgs[0].tool_call_id == "call_1"

    client.close()


def test_query_loop_tool_args_parse_error_does_not_crash(tmp_path: Path) -> None:
    # Model streams a tool_call with invalid JSON args; we must still emit a tool message.
    events = [
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_bad_args",
                                "function": {"name": "echo", "arguments": "{not-json"},
                            }
                        ]
                    }
                }
            ]
        },
        "[DONE]",
    ]

    def handler(request: httpx.Request) -> httpx.Response:
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

    from pydantic import BaseModel

    class EchoArgs(BaseModel):
        text: str

    @tool(name="echo", description="echo", input_model=EchoArgs)
    def echo(args: EchoArgs) -> str:
        return args.text

    reg = ToolRegistry()
    reg_tool = getattr(echo, "__ggbot_tool__")
    reg.register(reg_tool.spec, reg_tool.handler)

    transcript = Transcript(path=tmp_path / "t.jsonl")
    messages: list[ChatMessage] = [ChatMessage(role="system", content="sys")]

    run_query(
        client=client,
        registry=reg,
        transcript=transcript,
        messages=messages,
        user_text="do tool",
        max_turns=1,
        stream_printer=None,
    )

    tool_msgs = [m for m in messages if m.role == "tool"]
    assert tool_msgs and tool_msgs[0].tool_call_id == "call_bad_args"
    assert "Tool error" in (tool_msgs[0].content or "")

    client.close()


def test_run_query_auto_heals_missing_tool_messages_before_provider_call(tmp_path: Path) -> None:
    captured_payload: dict | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = json.loads(request.content.decode("utf-8"))
        # Return a simple assistant message with no tool calls.
        events = [
            {"choices": [{"delta": {"content": "ok"}}]},
            "[DONE]",
        ]
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

    # Prepare an interrupted history: assistant tool_calls but missing tool response.
    messages: list[ChatMessage] = [
        ChatMessage(role="system", content="sys"),
        ChatMessage(
            role="assistant",
            content="",
            tool_calls=[
                ToolCall(
                    id="call_missing",
                    function=ToolFunction(name="echo", arguments="{}"),
                )
            ],
        ),
    ]

    transcript = Transcript(path=tmp_path / "t.jsonl")
    reg = ToolRegistry()

    run_query(
        client=client,
        registry=reg,
        transcript=transcript,
        messages=messages,
        user_text="hi",
        max_turns=1,
        stream_printer=None,
    )

    assert captured_payload is not None
    sent = captured_payload.get("messages")
    assert isinstance(sent, list)

    # Validate the assistant tool_calls is immediately followed by a tool message.
    for idx, m in enumerate(sent):
        if m.get("role") == "assistant" and m.get("tool_calls"):
            next_msg = sent[idx + 1]
            assert next_msg.get("role") == "tool"
            assert next_msg.get("tool_call_id") == "call_missing"
            break
    else:
        raise AssertionError("Did not find assistant tool_calls in payload")

    client.close()


def test_run_query_sanitizes_orphan_tool_messages_before_provider_call(tmp_path: Path) -> None:
    captured_payload: dict | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = json.loads(request.content.decode("utf-8"))
        events = [
            {"choices": [{"delta": {"content": "ok"}}]},
            "[DONE]",
        ]
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"".join(_sse_bytes(events)),
        )

    client = OpenAICompatibleClient(
        base_url="https://example.test/v1",
        api_key="test",
        model="test-model",
        transport=httpx.MockTransport(handler),
    )

    # Corrupted history: a tool message appears without a preceding assistant tool_calls.
    messages: list[ChatMessage] = [
        ChatMessage(role="system", content="sys"),
        ChatMessage(role="tool", content="oops", tool_call_id="call_orphan", name="shell_run"),
    ]

    transcript = Transcript(path=tmp_path / "t.jsonl")
    reg = ToolRegistry()

    run_query(
        client=client,
        registry=reg,
        transcript=transcript,
        messages=messages,
        user_text="hi",
        max_turns=1,
        stream_printer=None,
    )

    assert captured_payload is not None
    sent = captured_payload.get("messages")
    assert isinstance(sent, list)
    # There should be no tool role messages without a preceding tool_calls block; we convert them to system.
    assert not any(m.get("role") == "tool" for m in sent)

    client.close()
