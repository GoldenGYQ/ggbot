from __future__ import annotations

import traceback
from dataclasses import dataclass
from collections.abc import Callable
import json

from ..providers.openai_client import OpenAIClientError, OpenAICompatibleClient
from ..tools.context import ToolContext
from ..tools.registry import ToolRegistry, parse_tool_arguments
from .transcript import Transcript
from .types import ChatMessage, ToolCall


@dataclass(frozen=True)
class QueryResult:
    messages: list[ChatMessage]


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


def _auto_heal_missing_tool_messages(*, messages: list[ChatMessage], transcript: Transcript) -> None:
    """Ensure any assistant tool_calls are followed by matching tool messages.

    Providers commonly hard-fail with HTTP 400 if an assistant message with tool_calls
    is not immediately followed by one tool message per tool_call_id.

    This can happen if a previous run was interrupted between receiving tool_calls
    and sending tool results (e.g. crash, kill, blocked input).
    """

    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg.role != "assistant" or not msg.tool_calls:
            i += 1
            continue

        tool_calls = msg.tool_calls
        expected_ids = [tc.id for tc in tool_calls]
        provided_ids: set[str] = set()

        j = i + 1
        while j < len(messages) and messages[j].role == "tool":
            tool_call_id = messages[j].tool_call_id
            if tool_call_id:
                provided_ids.add(tool_call_id)
            j += 1

        missing = [tc for tc in tool_calls if tc.id not in provided_ids]
        for tc in missing:
            tool_msg = ChatMessage(
                role="tool",
                content="Cancelled: missing tool response (auto-healed).",
                tool_call_id=tc.id,
                name=tc.function.name,
            )
            messages.insert(j, tool_msg)
            transcript.append("model_message", tool_msg.model_dump(exclude_none=True))
            transcript.append(
                "tool_result",
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "content_len": len(tool_msg.content),
                    "auto_healed": True,
                },
            )
            j += 1

        i = j


def _sanitize_orphan_tool_messages(*, messages: list[ChatMessage]) -> None:
    """Convert any orphan tool messages into system messages.

    Many OpenAI-compatible providers require:
    - tool messages only appear immediately after an assistant message that has tool_calls
    - and each tool message must correspond to one of those tool_call_id values

    If history is corrupted (e.g. a run crashed mid-turn), we might have tool messages
    that no longer have a valid preceding tool_calls block. Converting them to system
    preserves the text while making the sequence valid.
    """

    expecting_ids: set[str] | None = None

    for idx, msg in enumerate(list(messages)):
        if msg.role == "assistant" and msg.tool_calls:
            expecting_ids = {tc.id for tc in msg.tool_calls}
            continue

        if msg.role == "tool":
            if expecting_ids is None:
                name = msg.name or "tool"
                tool_call_id = msg.tool_call_id or "<missing>"
                messages[idx] = ChatMessage(
                    role="system",
                    content=(
                        "Orphan tool message was converted to system text (history repair).\n"
                        f"name={name} tool_call_id={tool_call_id}\n\n{msg.content}"
                    ),
                )
                continue

            tool_call_id = msg.tool_call_id
            if tool_call_id is None or tool_call_id not in expecting_ids:
                name = msg.name or "tool"
                bad_id = tool_call_id or "<missing>"
                messages[idx] = ChatMessage(
                    role="system",
                    content=(
                        "Unexpected tool message was converted to system text (history repair).\n"
                        f"name={name} tool_call_id={bad_id}\n\n{msg.content}"
                    ),
                )
                continue

            expecting_ids.remove(tool_call_id)
            if not expecting_ids:
                expecting_ids = None
            continue

        # Any non-tool message ends the tool response window.
        expecting_ids = None


def run_query(
    *,
    client: OpenAICompatibleClient,
    registry: ToolRegistry,
    transcript: Transcript,
    messages: list[ChatMessage],
    user_text: str,
    max_turns: int,
    stream_printer: Callable[[str], None] | None = None,
    tool_printer: Callable[[str, str], None] | None = None,
    tool_context: ToolContext | None = None,
    tool_limits: ToolLimits | None = None,
) -> QueryResult:
    messages.append(ChatMessage(role="user", content=user_text))
    transcript.append("model_message", messages[-1].model_dump(exclude_none=True))

    tools = registry.openai_tools()

    turns = 0
    budget = _ToolBudgetState(tool_limits or ToolLimits())
    while turns < max_turns:
        turns += 1

        # Heal any interrupted history before sending to the provider.
        _sanitize_orphan_tool_messages(messages=messages)
        _auto_heal_missing_tool_messages(messages=messages, transcript=transcript)

        def on_delta(text: str) -> None:
            if stream_printer:
                stream_printer(text)

        try:
            assistant_final = client.stream_and_collect(messages=messages, tools=tools, on_text_delta=on_delta)
        except OpenAIClientError as e:
            sys_msg = ChatMessage(
                role="system",
                content=(
                    "Provider error (OpenAI-compatible API call failed). "
                    "Fix configuration or retry.\n\n"
                    f"{e}"
                ),
            )
            messages.append(sys_msg)
            transcript.append("model_message", sys_msg.model_dump(exclude_none=True))
            transcript.append(
                "provider_error",
                {
                    "error": f"{type(e).__name__}: {e}",
                },
            )
            break
        except Exception as e:
            tb = traceback.format_exc()
            tb = tb if len(tb) <= 4000 else tb[:4000] + "\n…(traceback truncated)"
            sys_msg = ChatMessage(
                role="system",
                content=(
                    "Unexpected error while contacting provider.\n\n"
                    f"{type(e).__name__}: {e}\n\n{tb}"
                ),
            )
            messages.append(sys_msg)
            transcript.append("model_message", sys_msg.model_dump(exclude_none=True))
            transcript.append(
                "provider_error",
                {
                    "error": f"{type(e).__name__}: {e}",
                },
            )
            break

        assistant_msg = ChatMessage(
            role="assistant",
            content=assistant_final.content or "",
            tool_calls=assistant_final.tool_calls or None,
        )
        messages.append(assistant_msg)
        transcript.append("model_message", assistant_msg.model_dump(exclude_none=True))

        if not assistant_final.tool_calls:
            break

        for tool_call in assistant_final.tool_calls:
            _execute_tool_call(
                tool_call=tool_call,
                registry=registry,
                transcript=transcript,
                messages=messages,
                tool_printer=tool_printer,
                tool_context=tool_context,
                budget=budget,
            )

    return QueryResult(messages=messages)


def _execute_tool_call(
    *,
    tool_call: ToolCall,
    registry: ToolRegistry,
    transcript: Transcript,
    messages: list[ChatMessage],
    tool_printer: Callable[[str, str], None] | None = None,
    tool_context: ToolContext | None = None,
    budget: _ToolBudgetState | None = None,
) -> None:
    name = tool_call.function.name
    raw_arguments = tool_call.function.arguments or ""

    try:
        args = parse_tool_arguments(raw_arguments)
    except Exception as e:
        # Important: even if we can't parse args, we must still emit a tool message
        # for this tool_call_id, otherwise many providers will hard-fail with HTTP 400.
        tb = traceback.format_exc()
        tb = tb if len(tb) <= 4000 else tb[:4000] + "\n…(traceback truncated)"
        args = {}
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
        return

    transcript.append(
        "tool_call",
        {
            "id": tool_call.id,
            "name": name,
            "arguments": args,
        },
    )

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
            return

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
