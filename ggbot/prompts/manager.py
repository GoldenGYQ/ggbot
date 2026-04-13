from __future__ import annotations

from pathlib import Path

from ..core.config import Settings
from ..core.types import ChatMessage, ToolSpec
from .builder import PromptBuilder
from .repository import PromptRepository
from .types import PromptMode, RenderedPrompt, PromptContext


class PromptManager:
    def __init__(self, *, settings: Settings) -> None:
        prompt_dir = settings.prompt_dir or (settings.workspace_root / ".ggbot" / "prompts")
        self._settings = settings
        self._repository = PromptRepository(prompt_dir=prompt_dir)
        self._builder = PromptBuilder()

    @property
    def profile_name(self) -> str:
        return self._settings.prompt_profile

    @property
    def prompt_dir(self) -> Path:
        return self._settings.prompt_dir or (self._settings.workspace_root / ".ggbot" / "prompts")

    def build_rendered_prompt(self, *, mode: PromptMode, tool_specs: list[ToolSpec], thinking_enabled: bool = False) -> RenderedPrompt:
        profile = self._repository.load_profile(self.profile_name)
        context = PromptContext(
            mode=mode,
            workspace_root=self._settings.workspace_root,
            tool_specs=tool_specs,
            thinking_enabled=thinking_enabled,
        )
        return self._builder.render(profile=profile, context=context)

    def build_system_message(self, *, mode: PromptMode, tool_specs: list[ToolSpec], thinking_enabled: bool = False) -> ChatMessage:
        rendered = self.build_rendered_prompt(mode=mode, tool_specs=tool_specs, thinking_enabled=thinking_enabled)
        return ChatMessage(role="system", content=rendered.content)
