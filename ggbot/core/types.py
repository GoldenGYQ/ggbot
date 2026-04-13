from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field


Role = Literal["system", "user", "assistant", "tool", "thinking"]


class ToolFunction(BaseModel):
    name: str
    arguments: str = ""  # streamed as incremental JSON string in many OpenAI-compatible APIs


class ToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: ToolFunction


class ChatMessage(BaseModel):
    role: Role
    content: str

    # assistant tool-calling (OpenAI-compatible)
    tool_calls: list[ToolCall] | None = None

    # tool message fields
    tool_call_id: str | None = None
    name: str | None = None

    # thinking message fields (for models that support thinking/reasoning)
    thinking: str | None = None

    # raw content from model (for debugging and analysis)
    raw_content: str | None = None


class AssistantFinal(BaseModel):
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]

    def as_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass(frozen=True)
class StreamDelta:
    content: str = ""


@dataclass(frozen=True)
class StreamToolCallDelta:
    index: int
    tool_call_id: str | None
    name: str | None
    arguments_fragment: str | None


@dataclass(frozen=True)
class ThinkingConfig:
    """Configuration for thinking/reasoning functionality."""
    enabled: bool = False
    # Future: could add thinking style, max_length, etc.
