from __future__ import annotations

import re
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

from ..providers.types import ChatCompletionClient, ProviderError
from ..models.runtime_models import RuntimeEvent
from ..events.runtime_events import runtime_event
from ..state.transcript import Transcript
from ..models.protocol_models import ChatMessage, ToolCall


@dataclass(frozen=True)
class ModelTurnOutcome:
    tool_calls: list[ToolCall]
    should_stop: bool
    events: list[RuntimeEvent] = field(default_factory=list)


def extract_thinking_content(content: str) -> tuple[str | None, str]:
    """Extract thinking content from model output.

    Returns: (thinking_content, final_content)
    """
    if not content:
        return None, ""

    patterns = [
        (r"思考[：:]\s*(.*?)\s*\n\s*\n\s*回答[：:]\s*(.*)", True),
        (r"<thinking>(.*?)</thinking>\s*<answer>(.*?)</answer>", True),
        (r"思考开始[：:]\s*(.*?)\s*思考结束", False),
        (r"Reasoning[：:]\s*(.*?)\s*\n\s*\n\s*Answer[：:]\s*(.*)", True),
        (r"Thinking[：:]\s*(.*?)\s*\n\s*\n\s*Answer[：:]\s*(.*)", True),
        (r"Thinking[：:]\s*(.*?)\s*\n\s*\n\s*Response[：:]\s*(.*)", True),
        (r"<reasoning>(.*?)</reasoning>\s*<answer>(.*?)</answer>", True),
        (r"<reasoning>(.*?)</reasoning>\s*<response>(.*?)</response>", True),
        (r"首先，让我思考一下[：:]\s*(.*?)\s*现在，我的回答是[：:]\s*(.*)", True),
        (r"让我分析一下[：:]\s*(.*?)\s*基于以上分析，我的结论是[：:]\s*(.*)", True),
    ]

    for pattern, has_answer in patterns:
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            continue

        if has_answer:
            thinking = match.group(1).strip()
            answer = match.group(2).strip()
            return thinking, answer

        thinking = match.group(1).strip()
        remaining = re.sub(pattern, "", content, flags=re.DOTALL).strip()
        return thinking, remaining

    reasoning_indicators = [
        "因为", "所以", "因此", "由于", "考虑到", "基于",
        "because", "so", "therefore", "thus", "since", "given that",
        "首先", "其次", "然后", "最后", "另外", "而且",
        "first", "second", "then", "finally", "additionally", "moreover",
    ]

    lines = content.split("\n")
    if len(lines) > 1:
        first_part = lines[0].strip()
        if any(indicator in first_part for indicator in reasoning_indicators):
            thinking = first_part
            answer = "\n".join(lines[1:]).strip()
            if answer:
                return thinking, answer

    return None, content


def perform_model_turn(
    *,
    client: ChatCompletionClient,
    messages: list[ChatMessage],
    transcript: Transcript,
    tools: list[dict[str, Any]],
    stream_printer: Callable[[str], None] | None,
    thinking_enabled: bool,
    event_callback: Callable[[RuntimeEvent], None] | None = None,
) -> ModelTurnOutcome:
    events: list[RuntimeEvent] = []

    def add_event(event: RuntimeEvent):
        events.append(event)
        if event_callback:
            event_callback(event)

    def on_delta(text: str) -> None:
        if stream_printer:
            stream_printer(text)
        if event_callback:
            # assistant_delta typically doesn't go to transcript/final events
            # so we only call the callback
            event_callback(runtime_event("assistant_delta", {"delta": text}))

    try:
        assistant_final = client.stream_and_collect(messages=messages, tools=tools, on_text_delta=on_delta)
    except ProviderError as e:
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
        transcript.append("provider_error", {"error": f"{type(e).__name__}: {e}"})
        add_event(runtime_event("error", {"error": f"{type(e).__name__}: {e}"}))
        add_event(runtime_event("event", sys_msg.model_dump(exclude_none=True)))
        return ModelTurnOutcome(tool_calls=[], should_stop=True, events=events)
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
        transcript.append("provider_error", {"error": f"{type(e).__name__}: {e}"})
        add_event(runtime_event("error", {"error": f"{type(e).__name__}: {e}"}))
        add_event(runtime_event("event", sys_msg.model_dump(exclude_none=True)))
        return ModelTurnOutcome(tool_calls=[], should_stop=True, events=events)

    raw_content = assistant_final.content or ""
    final_content = raw_content

    if thinking_enabled and final_content:
        thinking_content, final_content = extract_thinking_content(final_content)
        if thinking_content:
            thinking_msg = ChatMessage(
                role="thinking",
                content=thinking_content,
                thinking=thinking_content,
                raw_content=raw_content,
            )
            messages.append(thinking_msg)
            transcript.append("model_message", thinking_msg.model_dump(exclude_none=True))
            transcript.append(
                "thinking",
                {
                    "thinking": thinking_content,
                    "content_len": len(thinking_content),
                    "raw_content": raw_content,
                },
            )
            add_event(runtime_event("event", thinking_msg.model_dump(exclude_none=True)))
            add_event(
                runtime_event(
                    "thinking",
                    {
                        "thinking": thinking_content,
                        "content_len": len(thinking_content),
                        "raw_content": raw_content,
                    },
                )
            )

    assistant_msg = ChatMessage(
        role="assistant",
        content=final_content,
        tool_calls=assistant_final.tool_calls or None,
        raw_content=raw_content,
    )
    messages.append(assistant_msg)
    transcript.append("model_message", assistant_msg.model_dump(exclude_none=True))
    add_event(runtime_event("response", assistant_msg.model_dump(exclude_none=True)))

    tool_calls = assistant_final.tool_calls or []
    return ModelTurnOutcome(tool_calls=tool_calls, should_stop=not bool(tool_calls), events=events)
