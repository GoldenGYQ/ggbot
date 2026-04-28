from __future__ import annotations

import re
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

from ..providers.types import ChatCompletionClient, GenerationInterrupted, ProviderError
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


def parse_plan_items(plan_text: str) -> list[dict[str, Any]]:
    """Parse plan text into structured items."""
    items = []
    lines = plan_text.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Match pattern: 1. [x] Task (tool) or 1. [ ] Task (tool)
        match = re.match(r"(\d+\.\s*)?\[(x| )\]\s*(.*?)(?:\s*\((.*?)\))?$", line)
        if match:
            items.append({
                "completed": match.group(2) == "x",
                "text": match.group(3).strip(),
                "tool": match.group(4).strip() if match.group(4) else None
            })
        else:
            # Fallback for lines without checkboxes
            items.append({
                "completed": False,
                "text": line,
                "tool": None
            })
    return items


def perform_model_turn(
    *,
    client: ChatCompletionClient,
    messages: list[ChatMessage],
    transcript: Transcript,
    tools: list[dict[str, Any]],
    stream_printer: Callable[[str], None] | None,
    thinking_enabled: bool,
    event_callback: Callable[[RuntimeEvent], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> ModelTurnOutcome:
    events: list[RuntimeEvent] = []
    accumulated_text = ""
    last_plan_content = ""
    streamed_thinking = ""
    streamed_reasoning_raw = ""

    def add_event(event: RuntimeEvent, *, include_in_result: bool = True) -> None:
        if include_in_result:
            events.append(event)
        if event_callback:
            event_callback(event)

    def handle_provider_error(error: Exception, *, include_traceback: bool) -> ModelTurnOutcome:
        err_text = f"{type(error).__name__}: {error}"
        if include_traceback:
            tb = traceback.format_exc()
            tb = tb if len(tb) <= 4000 else tb[:4000] + "\n... (traceback truncated)"
            content = (
                "Unexpected error while contacting provider.\n\n"
                f"{err_text}\n\n{tb}"
            )
        else:
            content = (
                "Provider error (OpenAI-compatible API call failed). "
                "Fix configuration or retry.\n\n"
                f"{error}"
            )

        sys_msg = ChatMessage(role="system", content=content)
        payload = sys_msg.model_dump(exclude_none=True)
        messages.append(sys_msg)
        transcript.append("model_message", payload)
        transcript.append("provider_error", {"error": err_text})
        add_event(runtime_event("error", {"error": err_text}))
        add_event(runtime_event("event", payload))
        return ModelTurnOutcome(tool_calls=[], should_stop=True, events=events)

    def on_delta(text: str) -> None:
        nonlocal accumulated_text, last_plan_content, streamed_thinking
        if should_stop is not None and should_stop():
            raise GenerationInterrupted("Generation interrupted by user request.")
        accumulated_text += text
        
        if stream_printer:
            stream_printer(text)
        
        # assistant_delta / plan_update are UI streaming signals:
        # emit to callback, but don't include in final per-turn result events.
        add_event(runtime_event("assistant_delta", {"delta": text}), include_in_result=False)

        if "<plan>" in accumulated_text and "</plan>" in accumulated_text:
            plan_match = re.search(r"<plan>(.*?)</plan>", accumulated_text, re.DOTALL)
            if plan_match:
                plan_content = plan_match.group(1).strip()
                if plan_content != last_plan_content:
                    last_plan_content = plan_content
                    plan_items = parse_plan_items(plan_content)
                    add_event(runtime_event("plan_update", {"plan": plan_items}), include_in_result=False)

        if thinking_enabled and "<thinking>" in accumulated_text and "</thinking>" in accumulated_text:
            thinking_match = re.search(r"<thinking>(.*?)</thinking>", accumulated_text, re.DOTALL)
            if thinking_match:
                thinking_text = thinking_match.group(1).strip()
                if thinking_text and thinking_text != streamed_thinking:
                    if thinking_text.startswith(streamed_thinking):
                        delta = thinking_text[len(streamed_thinking):]
                    else:
                        delta = thinking_text
                    streamed_thinking = thinking_text
                    if delta:
                        add_event(
                            runtime_event(
                                "thinking",
                                {
                                    "thinking": delta,
                                    "content_len": len(delta),
                                    "streaming": True,
                                },
                            ),
                            include_in_result=False,
                        )

    def on_reasoning_delta(text: str) -> None:
        nonlocal streamed_reasoning_raw
        if not thinking_enabled:
            return
        if should_stop is not None and should_stop():
            raise GenerationInterrupted("Generation interrupted by user request.")

        if text.startswith(streamed_reasoning_raw):
            delta = text[len(streamed_reasoning_raw):]
            streamed_reasoning_raw = text
        else:
            delta = text
            streamed_reasoning_raw += text

        if delta:
            add_event(
                runtime_event(
                    "thinking",
                    {
                        "thinking": delta,
                        "content_len": len(delta),
                        "streaming": True,
                    },
                ),
                include_in_result=False,
            )

    def on_raw_chunk(chunk: dict[str, Any]) -> None:
        # transcript.append("provider_chunk", {"chunk": chunk})
        add_event(
            runtime_event("provider_chunk", {"chunk": chunk}),
            include_in_result=False,
        )

    try:
        assistant_final = client.stream_and_collect(
            messages=messages,
            tools=tools,
            on_text_delta=on_delta,
            on_reasoning_delta=on_reasoning_delta,
            on_raw_chunk=on_raw_chunk,
            interrupt_callback=should_stop,
        )
    except GenerationInterrupted:
        interrupt_payload = {"message": "Generation interrupted by user request."}
        transcript.append("status", interrupt_payload)
        add_event(runtime_event("status", interrupt_payload))
        return ModelTurnOutcome(tool_calls=[], should_stop=True, events=events)
    except ProviderError as e:
        return handle_provider_error(e, include_traceback=False)
    except Exception as e:
        return handle_provider_error(e, include_traceback=True)

    raw_content = assistant_final.content or ""
    final_content = raw_content

    if thinking_enabled and final_content:
        thinking_content, final_content = extract_thinking_content(final_content)
        if thinking_content:
            thinking_payload = {
                "thinking": thinking_content,
                "content_len": len(thinking_content),
                "raw_content": raw_content,
            }
            thinking_msg = ChatMessage(
                role="thinking",
                content=thinking_content,
                thinking=thinking_content,
                raw_content=raw_content,
            )
            messages.append(thinking_msg)
            transcript.append("model_message", thinking_msg.model_dump(exclude_none=True))
            transcript.append("thinking", thinking_payload)
            add_event(runtime_event("event", thinking_msg.model_dump(exclude_none=True)))
            remaining_thinking = thinking_content
            if streamed_thinking and thinking_content.startswith(streamed_thinking):
                remaining_thinking = thinking_content[len(streamed_thinking):]
            if remaining_thinking:
                add_event(
                    runtime_event(
                        "thinking",
                        {
                            "thinking": remaining_thinking,
                            "content_len": len(remaining_thinking),
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
