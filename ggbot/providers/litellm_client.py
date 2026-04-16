from __future__ import annotations

from typing import Any, Callable

from ..domain.types import AssistantFinal, ChatMessage, StreamToolCallDelta, ToolCall, ToolFunction
from .types import ProviderError


def _to_dict(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    # pydantic v2
    if hasattr(obj, "model_dump") and callable(getattr(obj, "model_dump")):
        try:
            return obj.model_dump()  # type: ignore[no-any-return]
        except Exception:
            pass
    # pydantic v1
    if hasattr(obj, "dict") and callable(getattr(obj, "dict")):
        try:
            return obj.dict()  # type: ignore[no-any-return]
        except Exception:
            pass
    return {}


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


class LiteLLMClient:
    """A thin adapter that uses LiteLLM to call many providers via a unified API.

    We intentionally expose the same surface area used by the query loop:
    - stream_and_collect(...)
    - close()
    """

    def __init__(
        self,
        *,
        model: str,
        api_base: str | None = None,
        api_key: str | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        self._model = model
        self._api_base = api_base
        self._api_key = api_key
        self._timeout_s = timeout_s

    def close(self) -> None:
        # LiteLLM doesn't require an explicit close here.
        return

    def complete(self, *, messages: list[ChatMessage], tools: list[dict[str, Any]] | None) -> AssistantFinal:
        return self.stream_and_collect(messages=messages, tools=tools, on_text_delta=None)

    def stream_and_collect(
        self,
        *,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None,
        on_text_delta: Callable[[str], None] | None = None,
    ) -> AssistantFinal:
        # Import lazily so users who don't use this provider don't pay import cost.
        import litellm  # type: ignore

        content_parts: list[str] = []
        tool_calls: dict[int, ToolCall] = {}

        # LiteLLM expects OpenAI-style dict messages.
        # Convert thinking messages to system role for compatibility with APIs
        # that don't support the 'thinking' role (e.g., DeepSeek)
        payload_messages = []
        for m in messages:
            msg_dict = m.model_dump(exclude_none=True)
            if msg_dict.get("role") == "thinking":
                # Convert thinking to system role for API compatibility
                msg_dict["role"] = "system"
                # Add prefix to indicate this was originally thinking content
                if "content" in msg_dict:
                    msg_dict["content"] = f"[Thinking] {msg_dict['content']}"
            payload_messages.append(msg_dict)

        # Use streaming so we can surface incremental text.
        try:
            stream = litellm.completion(
                model=self._model,
                messages=payload_messages,
                tools=tools,
                stream=True,
                api_base=self._api_base,
                api_key=self._api_key,
                timeout=self._timeout_s,
            )

            for chunk in stream:
                obj = _to_dict(chunk)
                choices = obj.get("choices") or []
                if not choices:
                    continue

                c0 = choices[0] or {}
                delta = c0.get("delta") or {}

                text = delta.get("content")
                if text:
                    text_s = str(text)
                    if on_text_delta is not None:
                        on_text_delta(text_s)
                    content_parts.append(text_s)

                tc_list = delta.get("tool_calls") or []
                for tc in tc_list:
                    try:
                        index = int(tc.get("index", 0))
                    except Exception:
                        index = 0
                    tc_id = tc.get("id")
                    fn = tc.get("function") or {}
                    name = fn.get("name")
                    args_frag = fn.get("arguments")

                    _merge_tool_call_delta(
                        tool_calls,
                        StreamToolCallDelta(
                            index=index,
                            tool_call_id=tc_id,
                            name=name,
                            arguments_fragment=args_frag,
                        ),
                    )

                finish_reason = c0.get("finish_reason")
                if finish_reason:
                    # Common values: "stop", "tool_calls", "length".
                    # We break once finish is signaled after processing any final deltas.
                    break
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"LiteLLM provider call failed: {type(e).__name__}: {e}") from e

        return AssistantFinal(
            content="".join(content_parts),
            tool_calls=[tool_calls[i] for i in sorted(tool_calls)],
        )
