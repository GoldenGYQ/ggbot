from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Protocol

from ..tools.context import ToolContext
from ..tools.registry import ToolRegistry, parse_tool_arguments
from ..domain.domain import RuntimeEvent, RuntimeEventType
from ..events.runtime_events import runtime_event
from ..state.transcript import Transcript
from ..domain.types import ChatMessage, ToolCall


class ToolBudgetChecker(Protocol):
    def check_and_record(self, *, name: str, args: dict) -> str | None:
        ...


@dataclass
class ToolExecutionOutcome:
    events: list[RuntimeEvent] = field(default_factory=list)


def _emit_event(outcome: ToolExecutionOutcome, event_type: RuntimeEventType, data: dict) -> None:
    outcome.events.append(runtime_event(event_type, data))


def execute_tool_call(
    *,
    tool_call: ToolCall,
    registry: ToolRegistry,
    transcript: Transcript,
    messages: list[ChatMessage],
    tool_printer: Callable[[str, str], None] | None = None,
    tool_context: ToolContext | None = None,
    budget: ToolBudgetChecker | None = None,
) -> ToolExecutionOutcome:
    outcome = ToolExecutionOutcome()
    name = tool_call.function.name
    raw_arguments = tool_call.function.arguments or ""

    try:
        args = parse_tool_arguments(raw_arguments)
    except Exception as e:
        tb = traceback.format_exc()
        tb = tb if len(tb) <= 4000 else tb[:4000] + "\n…(traceback truncated)"
        result_text = (
            f"Tool error: failed to parse tool arguments for '{name}': {type(e).__name__}: {e}\n"
            f"Raw arguments:\n{raw_arguments}\n\n{tb}"
        )

        transcript.append(
            "tool_call",
            {
                "id": tool_call.id,
                "name": name,
                "arguments": None,
                "raw_arguments": raw_arguments,
                "parse_error": f"{type(e).__name__}: {e}",
            },
        )

        if tool_printer is not None:
            tool_printer(name, result_text)

        tool_msg = ChatMessage(
            role="tool",
            content=result_text,
            tool_call_id=tool_call.id,
            name=name,
        )
        messages.append(tool_msg)
        transcript.append("model_message", tool_msg.model_dump(exclude_none=True))
        transcript.append(
            "tool_result",
            {
                "id": tool_call.id,
                "name": name,
                "content_len": len(tool_msg.content),
                "error": True,
            },
        )
        _emit_event(outcome, "tool_call", {
            "id": tool_call.id,
            "name": name,
            "arguments": None,
            "raw_arguments": raw_arguments,
            "parse_error": f"{type(e).__name__}: {e}",
        })
        _emit_event(outcome, "event", tool_msg.model_dump(exclude_none=True))
        _emit_event(outcome, "tool_result", {
            "id": tool_call.id,
            "name": name,
            "content_len": len(tool_msg.content),
            "error": True,
        })
        return outcome

    transcript.append(
        "tool_call",
        {
            "id": tool_call.id,
            "name": name,
            "arguments": args,
        },
    )
    _emit_event(outcome, "tool_call", {
        "id": tool_call.id,
        "name": name,
        "arguments": args,
    })

    if budget is not None:
        cancel_reason = budget.check_and_record(name=name, args=args)
        if cancel_reason is not None:
            result_text = (
                f"Cancelled: {cancel_reason}.\n"
                "Please stop repeating this tool call and use the results already obtained."
            )

            if tool_printer is not None:
                tool_printer(name, result_text)

            tool_msg = ChatMessage(
                role="tool",
                content=result_text,
                tool_call_id=tool_call.id,
                name=name,
            )
            messages.append(tool_msg)
            transcript.append("model_message", tool_msg.model_dump(exclude_none=True))
            transcript.append(
                "tool_result",
                {
                    "id": tool_call.id,
                    "name": name,
                    "content_len": len(tool_msg.content),
                    "error": True,
                    "budget_exceeded": True,
                },
            )
            _emit_event(outcome, "event", tool_msg.model_dump(exclude_none=True))
            _emit_event(outcome, "tool_result", {
                "id": tool_call.id,
                "name": name,
                "content_len": len(tool_msg.content),
                "error": True,
                "budget_exceeded": True,
            })
            return outcome

    try:
        call_ctx = tool_context.for_call(tool_name=name, tool_call_id=tool_call.id) if tool_context else None
        result = registry.call(name, args, ctx=call_ctx)
        result_text = str(result)
    except Exception as e:
        tb = traceback.format_exc()
        tb = tb if len(tb) <= 4000 else tb[:4000] + "\n…(traceback truncated)"
        result_text = f"Tool error: {type(e).__name__}: {e}\n\n{tb}"

    if tool_printer is not None:
        tool_printer(name, result_text)

    tool_msg = ChatMessage(
        role="tool",
        content=result_text,
        tool_call_id=tool_call.id,
        name=name,
    )
    messages.append(tool_msg)
    transcript.append("model_message", tool_msg.model_dump(exclude_none=True))
    transcript.append(
        "tool_result",
        {
            "id": tool_call.id,
            "name": name,
            "content_len": len(tool_msg.content),
        },
    )
    _emit_event(outcome, "event", tool_msg.model_dump(exclude_none=True))
    _emit_event(outcome, "tool_result", {
        "id": tool_call.id,
        "name": name,
        "content_len": len(tool_msg.content),
    })

    return outcome
