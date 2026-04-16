from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable
import json

from ..providers.types import ChatCompletionClient
from ..tools.context import ToolContext
from ..tools.registry import ToolRegistry
from ..transport.transcript_contract import TranscriptEventType
from .history_repair import auto_heal_missing_tool_messages, sanitize_orphan_tool_messages
from .model_interaction import extract_thinking_content, perform_model_turn
from ..models.runtime_models import RuntimeEvent
from ..events.runtime_events import runtime_event
from .tool_execution import execute_tool_call
from ..state.transcript import Transcript
from ..models.protocol_models import ChatMessage


@dataclass
class QueryResult:
    messages: list[ChatMessage]
    turns_used: int = 0
    events: list[RuntimeEvent] = field(default_factory=list)


@dataclass
class ToolLimits:
    max_tool_calls: int = 30
    max_tool_calls_per_tool: int = 12
    max_tool_calls_same_args: int = 3


@dataclass
class _ToolBudgetState:
    limits: ToolLimits
    total: int = 0
    per_tool: dict[str, int] = None  # type: ignore[assignment]
    per_tool_args: dict[tuple[str, str], int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.per_tool is None:
            self.per_tool = {}
        if self.per_tool_args is None:
            self.per_tool_args = {}

    def check_and_record(self, *, name: str, args: dict) -> str | None:
        """Return cancel reason if budget exceeded, else None."""
        self.total += 1
        if self.total > self.limits.max_tool_calls:
            return f"Tool budget exceeded: max_tool_calls={self.limits.max_tool_calls}"

        self.per_tool[name] = self.per_tool.get(name, 0) + 1
        if self.per_tool[name] > self.limits.max_tool_calls_per_tool:
            return (
                "Tool budget exceeded: "
                f"tool={name} max_per_tool={self.limits.max_tool_calls_per_tool}"
            )

        args_key = json.dumps(args, ensure_ascii=False, sort_keys=True)
        k = (name, args_key)
        self.per_tool_args[k] = self.per_tool_args.get(k, 0) + 1
        if self.per_tool_args[k] > self.limits.max_tool_calls_same_args:
            return (
                "Tool budget exceeded: "
                f"tool={name} max_same_args={self.limits.max_tool_calls_same_args}"
            )

        return None


def _extract_thinking_content(content: str) -> tuple[str | None, str]:
    # Backward-compatible export for tests/importers.
    return extract_thinking_content(content)


def run_query(
    *,
    client: ChatCompletionClient,
    registry: ToolRegistry,
    transcript: Transcript,
    messages: list[ChatMessage],
    user_text: str,
    max_turns: int,
    stream_printer: Callable[[str], None] | None = None,
    tool_printer: Callable[[str, str], None] | None = None,
    tool_context: ToolContext | None = None,
    tool_limits: ToolLimits | None = None,
    thinking_enabled: bool = False,
) -> QueryResult:
    runtime_events: list[RuntimeEvent] = []

    messages.append(ChatMessage(role="user", content=user_text))
    transcript.append("model_message", messages[-1].model_dump(exclude_none=True))

    tools = registry.openai_tools()

    turns = 0
    budget = _ToolBudgetState(tool_limits or ToolLimits())

    # Record turn information to transcript
    transcript.append("turn_info", {
        "max_turns": max_turns,
        "start_turn": 0,
    })

    while turns < max_turns:
        turns += 1

        # Record current turn to transcript
        transcript.append("turn_update", {
            "current_turn": turns,
            "max_turns": max_turns,
        })
        runtime_events.append(runtime_event("turn_update", {"current_turn": turns, "max_turns": max_turns}))

        # Heal any interrupted history before sending to the provider.
        sanitize_orphan_tool_messages(messages=messages)
        auto_heal_missing_tool_messages(messages=messages, transcript=transcript)

        turn_outcome = perform_model_turn(
            client=client,
            messages=messages,
            transcript=transcript,
            tools=tools,
            stream_printer=stream_printer,
            thinking_enabled=thinking_enabled,
        )
        runtime_events.extend(turn_outcome.events)

        if turn_outcome.should_stop:
            break

        for tool_call in turn_outcome.tool_calls:
            tool_outcome = execute_tool_call(
                tool_call=tool_call,
                registry=registry,
                transcript=transcript,
                messages=messages,
                tool_printer=tool_printer,
                tool_context=tool_context,
                budget=budget,
            )
            runtime_events.extend(tool_outcome.events)

    # Record final turn information
    # Check if we have tool calls from the last assistant message
    last_has_tool_calls = False
    for msg in reversed(messages):
        if msg.role == "assistant":
            last_has_tool_calls = bool(msg.tool_calls)
            break

    transcript.append("turn_complete", {
        "turns_used": turns,
        "max_turns": max_turns,
        "completed": turns < max_turns or not last_has_tool_calls,
    })
    runtime_events.append(
        runtime_event(
            "turn_complete",
            {
                "turns_used": turns,
                "max_turns": max_turns,
                "completed": turns < max_turns or not last_has_tool_calls,
            },
        )
    )

    return QueryResult(messages=messages, turns_used=turns, events=runtime_events)

