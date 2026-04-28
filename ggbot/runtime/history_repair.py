from __future__ import annotations

from ..models.protocol_models import ChatMessage


def auto_heal_missing_tool_messages(
    *,
    messages: list[ChatMessage],
    persist_to_transcript: bool = False,
) -> None:
    """Ensure any assistant tool_calls are followed by matching tool messages."""

    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg.role != "assistant" or not msg.tool_calls:
            i += 1
            continue

        tool_calls = msg.tool_calls
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
            j += 1

        i = j


def sanitize_orphan_tool_messages(*, messages: list[ChatMessage]) -> None:
    """Convert orphan tool messages to system text to keep provider payload valid."""

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

        expecting_ids = None
