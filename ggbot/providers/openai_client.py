from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

import httpx

from ..core.types import AssistantFinal, ChatMessage, StreamDelta, StreamToolCallDelta, ToolCall, ToolFunction


class OpenAIClientError(Exception):
    pass


@dataclass
class StreamEvent:
    delta: StreamDelta | None = None
    tool_call_delta: StreamToolCallDelta | None = None
    done: bool = False


def _iter_sse_data_lines(lines: Iterable[str]) -> Iterable[str]:
    for raw in lines:
        if not raw:
            continue
        line = raw.strip()
        if not line.startswith("data:"):
            continue
        data = line[len("data:") :].strip()
        yield data


def _merge_tool_call_delta(tool_calls: dict[int, ToolCall], delta: StreamToolCallDelta) -> None:
    idx = delta.index
    if idx not in tool_calls:
        tool_calls[idx] = ToolCall(
            id=delta.tool_call_id or f"tool_{idx}",
            function=ToolFunction(name=delta.name or "", arguments=""),
        )

    current = tool_calls[idx]
    if delta.tool_call_id:
        current.id = delta.tool_call_id
    if delta.name:
        current.function.name = delta.name
    if delta.arguments_fragment:
        current.function.arguments += delta.arguments_fragment


class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout,
            transport=transport,
        )
        self._model = model

    def close(self) -> None:
        self._client.close()

    def stream_chat_completions(
        self,
        *,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> Iterable[StreamEvent]:
        payload: dict[str, Any] = {
            "model": self._model,
            "stream": True,
            "messages": [m.model_dump(exclude_none=True) for m in messages],
        }
        if tools:
            payload["tools"] = tools
            if tool_choice is not None:
                payload["tool_choice"] = tool_choice

        with self._client.stream("POST", "/chat/completions", json=payload) as resp:
            if resp.status_code >= 400:
                # Streaming responses in httpx don't have `.text` available until read.
                # Read the body eagerly so we can surface a useful error message.
                try:
                    resp.read()
                    body_text = resp.text
                except Exception:
                    body_text = "<failed to read error body>"
                raise OpenAIClientError(f"HTTP {resp.status_code}: {body_text}")

            for data in _iter_sse_data_lines(resp.iter_lines()):
                if data == "[DONE]":
                    yield StreamEvent(done=True)
                    return

                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue

                choices = obj.get("choices") or []
                if not choices:
                    continue

                delta = choices[0].get("delta") or {}
                if "content" in delta and delta["content"] is not None:
                    yield StreamEvent(delta=StreamDelta(content=str(delta["content"])))

                if "tool_calls" in delta and delta["tool_calls"] is not None:
                    for tc in delta["tool_calls"]:
                        index = int(tc.get("index", 0))
                        tc_id = tc.get("id")
                        fn = tc.get("function") or {}
                        name = fn.get("name")
                        args_frag = fn.get("arguments")
                        yield StreamEvent(
                            tool_call_delta=StreamToolCallDelta(
                                index=index,
                                tool_call_id=tc_id,
                                name=name,
                                arguments_fragment=args_frag,
                            )
                        )

    def stream_and_collect(
        self,
        *,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None,
        on_text_delta: callable | None = None,
    ) -> AssistantFinal:
        content_parts: list[str] = []
        tool_calls: dict[int, ToolCall] = {}

        for event in self.stream_chat_completions(messages=messages, tools=tools):
            if event.delta:
                if on_text_delta is not None:
                    on_text_delta(event.delta.content)
                content_parts.append(event.delta.content)
            if event.tool_call_delta:
                _merge_tool_call_delta(tool_calls, event.tool_call_delta)
            if event.done:
                break

        return AssistantFinal(
            content="".join(content_parts),
            tool_calls=[tool_calls[i] for i in sorted(tool_calls)],
        )

    def complete(self, *, messages: list[ChatMessage], tools: list[dict[str, Any]] | None) -> AssistantFinal:
        return self.stream_and_collect(messages=messages, tools=tools)
