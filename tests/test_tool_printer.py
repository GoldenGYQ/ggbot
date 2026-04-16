from __future__ import annotations

from typing import Any

from ggbot.runtime.agent_loop import run_query
from ggbot.state.transcript import Transcript
from ggbot.models.protocol_models import AssistantFinal, ChatMessage, ToolCall, ToolFunction, ToolSpec
from ggbot.tools.registry import ToolRegistry


class _FakeClient:
    def __init__(self) -> None:
        self.called = 0

    def close(self) -> None:
        return

    def complete(self, *, messages: list[ChatMessage], tools):
        return self.stream_and_collect(messages=messages, tools=tools, on_text_delta=None)

    def stream_and_collect(self, *, messages: list[ChatMessage], tools: Any, on_text_delta: Any = None):
        # First assistant turn: request tool call
        self.called += 1
        if self.called == 1:
            return AssistantFinal(
                content="",
                tool_calls=[
                    ToolCall(id="1", type="function", function=ToolFunction(name="echo", arguments='{"x": 1}'))
                ],
            )
        # Second assistant turn: finish
        return AssistantFinal(content="done", tool_calls=[])


def test_tool_printer_called(tmp_path) -> None:
    registry = ToolRegistry()

    def echo(args: dict[str, Any], ctx) -> str:
        _ = ctx
        return f"ok:{args['x']}"

    spec = ToolSpec(
        name='echo',
        description='echo',
        parameters={
            'type': 'object',
            'properties': {'x': {'type': 'integer'}},
            'required': ['x'],
            'additionalProperties': False,
        },
    )
    registry.register(spec, echo)

    printed: list[tuple[str, str]] = []

    def tool_printer(name: str, output: str) -> None:
        printed.append((name, output))

    messages: list[ChatMessage] = [ChatMessage(role='system', content='hi')]
    run_query(
        client=_FakeClient(),
        registry=registry,
        transcript=Transcript(path=tmp_path / 't.jsonl'),
        messages=messages,
        user_text='go',
        max_turns=3,
        stream_printer=None,
        tool_printer=tool_printer,
    )

    assert printed == [('echo', 'ok:1')]
