from __future__ import annotations

from pathlib import Path

from ggbot.app.config import Settings
from ggbot.models.protocol_models import ToolSpec
from ggbot.prompts import PromptManager


def test_prompt_manager_renders_default_profile(tmp_path: Path) -> None:
    settings = Settings.load(workspace_root=tmp_path)
    manager = PromptManager(settings=settings)

    # Create mock tool specs for testing
    tool_specs = [
        ToolSpec(
            name="file_read",
            description="Read file contents",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "File path"}},
                "required": ["path"],
            },
        ),
        ToolSpec(
            name="file_write",
            description="Write content to file",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "content": {"type": "string", "description": "File content"},
                },
                "required": ["path", "content"],
            },
        ),
    ]

    msg = manager.build_system_message(mode="repl", tool_specs=tool_specs)

    assert msg.role == "system"
    assert "**Mode**: repl" in msg.content
    assert "file_read:" in msg.content  # Now appears as "file_read: description"
    assert "file_write:" in msg.content


def test_prompt_manager_includes_custom_profile_file(tmp_path: Path) -> None:
    prompts_dir = tmp_path / ".ggbot" / "prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "default.md").write_text("Custom project prompt layer", encoding="utf-8")

    settings = Settings.load(workspace_root=tmp_path)
    manager = PromptManager(settings=settings)

    rendered = manager.build_rendered_prompt(mode="chat", tool_specs=[])

    assert rendered.profile_name == "default"
    assert "profile:default" in rendered.layer_names
    assert "Custom project prompt layer" in rendered.content
