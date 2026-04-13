from __future__ import annotations

from pathlib import Path

from .types import PromptLayer, PromptProfile


def _default_layers() -> list[PromptLayer]:
    return [
        PromptLayer(
            name="role",
            template=(
                "You are GGbot, a pragmatic coding agent. Solve tasks end-to-end, "
                "make minimal safe changes, and keep responses concise and actionable."
            ),
        ),
        PromptLayer(
            name="workflow",
            template=(
                "Mode: {mode}\n"
                "Workspace root: {workspace_root}\n"
                "Use tools when needed. Prefer inspection before modification."
            ),
        ),
        PromptLayer(
            name="tooling",
            template=(
                "Available tools:\n{tool_list}\n"
                "When editing files, preserve existing style and avoid unrelated refactors."
            ),
        ),
        PromptLayer(
            name="safety",
            template=(
                "Never access paths outside workspace_root.\n"
                "For destructive actions, ask for confirmation first."
            ),
        ),
    ]


class PromptRepository:
    def __init__(self, *, prompt_dir: Path) -> None:
        self._prompt_dir = prompt_dir

    def load_profile(self, profile_name: str) -> PromptProfile:
        layers = _default_layers()

        profile_path = self._prompt_dir / f"{profile_name}.md"
        if profile_path.exists():
            custom = profile_path.read_text(encoding="utf-8").strip()
            if custom:
                layers.append(PromptLayer(name=f"profile:{profile_name}", template=custom))

        return PromptProfile(name=profile_name, layers=layers)
