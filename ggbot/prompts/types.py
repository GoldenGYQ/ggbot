from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


PromptMode = Literal["chat", "repl", "tui"]


@dataclass(frozen=True)
class PromptContext:
    mode: PromptMode
    workspace_root: Path
    tool_names: list[str]


@dataclass(frozen=True)
class PromptLayer:
    name: str
    template: str
    enabled: bool = True


@dataclass(frozen=True)
class PromptProfile:
    name: str
    layers: list[PromptLayer]


@dataclass(frozen=True)
class RenderedPrompt:
    profile_name: str
    layer_names: list[str]
    content: str
