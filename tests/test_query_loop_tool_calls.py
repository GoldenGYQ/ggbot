from pathlib import Path

from ggbot.api.permission_manager import get_permission_manager
from ggbot.models.protocol_models import AssistantFinal,ChatMessage, ToolCall, ToolFunction
from ggbot.runtime.agent_loop import ToolLimits, run_query
from ggbot.tools.registry import ToolRegistry, tool
from ggbot.state.transcript import Transcript

def test_query_loop_executes_tool_calls(tmp_path: Path) -> None:
    class _Client:
        def __init__(self) -> None:
            self.n = 0

        def close(self) -> None:
            return

        def complete(self, *, messages: list[ChatMessage], tools):
            return self.stream_and_collect(messages=messages, tools=tools, on_text_delta=None)

        def stream_and_collect(self, *, messages: list[ChatMessage], tools, on_text_delta=None):
            self.n += 1
            if self.n == 1:
                return AssistantFinal(
                    content="",
                    tool_calls=[
                        ToolCall(
                            id="call_1",
                            function=ToolFunction(name="echo", arguments='{"text":"hi"}'),
                        )
                    ],
                )
            return AssistantFinal(content="ok", tool_calls=[])

    client = _Client()

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
    class _Client:
        def close(self) -> None:
            return

        def complete(self, *, messages: list[ChatMessage], tools):
            return self.stream_and_collect(messages=messages, tools=tools, on_text_delta=None)

        def stream_and_collect(self, *, messages: list[ChatMessage], tools, on_text_delta=None):
            return AssistantFinal(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call_bad_args",
                        function=ToolFunction(name="echo", arguments="{not-json"),
                    )
                ],
            )

    client = _Client()

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
    captured_messages: list[dict] | None = None

    class _RecordingClient:
        def close(self) -> None:
            return

        def complete(self, *, messages: list[ChatMessage], tools):
            return self.stream_and_collect(messages=messages, tools=tools, on_text_delta=None)

        def stream_and_collect(self, *, messages: list[ChatMessage], tools, on_text_delta=None):
            nonlocal captured_messages
            captured_messages = [m.model_dump(exclude_none=True) for m in messages]
            return AssistantFinal(content="ok", tool_calls=[])

    client = _RecordingClient()

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

    assert captured_messages is not None
    sent = captured_messages

    # Validate the assistant tool_calls is immediately followed by a tool message.
    for idx, m in enumerate(sent):
        if m.get("role") == "assistant" and m.get("tool_calls"):
            next_msg = sent[idx + 1]
            assert next_msg.get("role") == "tool"
            assert next_msg.get("tool_call_id") == "call_missing"
            break
    else:
        raise AssertionError("Did not find assistant tool_calls in payload")

    # Auto-healed synthetic tool messages should stay in-memory only.
    # Persisting them at transcript tail can create out-of-order orphan tool entries.
    events = list(transcript.iter_events())
    assert not any(
        ev.get("type") == "model_message"
        and (ev.get("data") or {}).get("role") == "tool"
        and (ev.get("data") or {}).get("tool_call_id") == "call_missing"
        for ev in events
    )

    client.close()


def test_query_loop_cancels_repeated_identical_tool_calls(tmp_path: Path) -> None:
    # Model asks for the same tool with the same args repeatedly across turns.
    # Budget should cancel after max_tool_calls_same_args is exceeded.

    class _RepeatClient:
        def __init__(self) -> None:
            self.n = 0

        def close(self) -> None:
            return

        def complete(self, *, messages: list[ChatMessage], tools):
            return self.stream_and_collect(messages=messages, tools=tools, on_text_delta=None)

        def stream_and_collect(self, *, messages: list[ChatMessage], tools, on_text_delta=None):
            self.n += 1
            # Always request the same tool call.
            return AssistantFinal(
                content="",
                tool_calls=[
                    ToolCall(
                        id=f"call_{self.n}",
                        function=ToolFunction(
                            name="duckduckgo_search",
                            arguments='{"query":"x","max_results":1}',
                        ),
                    )
                ],
            )

    calls: list[dict] = []

    from pydantic import BaseModel

    class Args(BaseModel):
        query: str
        max_results: int = 1

    @tool(name="duckduckgo_search", description="ddg", input_model=Args)
    def ddg(args: Args) -> str:
        calls.append(args.model_dump())
        return "ok"

    reg = ToolRegistry()
    reg_tool = getattr(ddg, "__ggbot_tool__")
    reg.register(reg_tool.spec, reg_tool.handler)

    transcript = Transcript(path=tmp_path / "t.jsonl")
    messages: list[ChatMessage] = [ChatMessage(role="system", content="sys")]

    run_query(
        client=_RepeatClient(),
        registry=reg,
        transcript=transcript,
        messages=messages,
        user_text="search",
        max_turns=6,
        stream_printer=None,
        tool_limits=ToolLimits(max_tool_calls=100, max_tool_calls_per_tool=100, max_tool_calls_same_args=2),
    )

    # Tool should have executed only twice; afterwards it gets cancelled.
    assert len(calls) == 2
    tool_msgs = [m for m in messages if m.role == "tool"]
    assert any("Tool budget exceeded" in (m.content or "") for m in tool_msgs)


def test_run_query_sanitizes_orphan_tool_messages_before_provider_call(tmp_path: Path) -> None:
    captured_messages: list[dict] | None = None

    class _RecordingClient:
        def close(self) -> None:
            return

        def complete(self, *, messages: list[ChatMessage], tools):
            return self.stream_and_collect(messages=messages, tools=tools, on_text_delta=None)

        def stream_and_collect(self, *, messages: list[ChatMessage], tools, on_text_delta=None):
            nonlocal captured_messages
            captured_messages = [m.model_dump(exclude_none=True) for m in messages]
            return AssistantFinal(content="ok", tool_calls=[])

    client = _RecordingClient()

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

    assert captured_messages is not None
    sent = captured_messages
    # There should be no tool role messages without a preceding tool_calls block; we convert them to system.
    assert not any(m.get("role") == "tool" for m in sent)

    client.close()


def test_run_query_propagates_permission_context_into_tool_threads(tmp_path: Path) -> None:
    class _Client:
        def __init__(self) -> None:
            self.n = 0

        def close(self) -> None:
            return

        def complete(self, *, messages: list[ChatMessage], tools):
            return self.stream_and_collect(
                messages=messages,
                tools=tools,
                on_text_delta=None,
                on_reasoning_delta=None,
            )

        def stream_and_collect(
            self,
            *,
            messages: list[ChatMessage],
            tools,
            on_text_delta=None,
            on_reasoning_delta=None,
            **kwargs,
        ):
            self.n += 1
            if self.n == 1:
                return AssistantFinal(
                    content="",
                    tool_calls=[
                        ToolCall(
                            id="call_perm",
                            function=ToolFunction(name="needs_permission", arguments="{}"),
                        )
                    ],
                )
            return AssistantFinal(content="ok", tool_calls=[])

    from pydantic import BaseModel

    class EmptyArgs(BaseModel):
        pass

    @tool(name="needs_permission", description="request permission", input_model=EmptyArgs)
    def needs_permission(args: EmptyArgs) -> str:
        allowed, reason, _ = get_permission_manager().request(
            tool_name="shell_run",
            arguments={"command": "echo hi"},
            timeout_s=0.02,
        )
        return f"allowed={allowed}; reason={reason}"

    reg = ToolRegistry()
    reg_tool = getattr(needs_permission, "__ggbot_tool__")
    reg.register(reg_tool.spec, reg_tool.handler)

    transcript = Transcript(path=tmp_path / "t_perm.jsonl")
    messages: list[ChatMessage] = [ChatMessage(role="system", content="sys")]
    emitted = []
    manager = get_permission_manager()
    token = manager.set_request_context(
        connection_id="conn-1",
        session_id="session-1",
        event_callback=lambda event: emitted.append(event),
    )
    try:
        run_query(
            client=_Client(),
            registry=reg,
            transcript=transcript,
            messages=messages,
            user_text="do tool",
            max_turns=2,
            stream_printer=None,
        )
    finally:
        manager.reset_request_context(token)

    assert any(ev.type == "permission_request" for ev in emitted)
