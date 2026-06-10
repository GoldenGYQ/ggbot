"""Tests for thinking functionality."""

from __future__ import annotations

import json
from pathlib import Path

from ggbot.runtime.agent_loop import _extract_thinking_content
from ggbot.models.protocol_models import ChatMessage, ThinkingConfig
from ggbot.app.config import Settings
from ggbot.prompts.types import PromptContext
from ggbot.prompts.builder import PromptBuilder
from ggbot.prompts.repository import PromptRepository, _default_layers


@pytest.mark.unit
def test_thinking_extraction() -> None:
    """Test extraction of thinking content from various formats."""

    # Test Chinese format
    content = "思考：这是一个测试思考\n\n回答：这是回答"
    thinking, answer = _extract_thinking_content(content)
    assert thinking == "这是一个测试思考"
    assert answer == "这是回答"

    # Test English format - Thinking: ... Answer: ...
    content = "Thinking: This is reasoning\n\nAnswer: This is answer"
    thinking, answer = _extract_thinking_content(content)
    assert thinking == "This is reasoning"
    assert answer == "This is answer"

    # Test English format - Thinking: ... Response: ...
    content = "Thinking: Another reasoning\n\nResponse: Another response"
    thinking, answer = _extract_thinking_content(content)
    assert thinking == "Another reasoning"
    assert answer == "Another response"

    # Test XML format
    content = "<thinking>Internal thought</thinking><answer>Final answer</answer>"
    thinking, answer = _extract_thinking_content(content)
    assert thinking == "Internal thought"
    assert answer == "Final answer"

    # Test no thinking
    content = "Direct answer without thinking"
    thinking, answer = _extract_thinking_content(content)
    assert thinking is None
    assert answer == "Direct answer without thinking"


@pytest.mark.unit
def test_chatmessage_with_thinking() -> None:
    """Test ChatMessage serialization with thinking field."""

    # Create thinking message
    msg = ChatMessage(
        role="thinking",
        content="Thinking content",
        thinking="Thinking content",
    )

    # Verify fields
    assert msg.role == "thinking"
    assert msg.content == "Thinking content"
    assert msg.thinking == "Thinking content"

    # Test serialization
    data = msg.model_dump(exclude_none=True)
    assert data["role"] == "thinking"
    assert data["content"] == "Thinking content"
    assert data["thinking"] == "Thinking content"

    # Test deserialization
    restored = ChatMessage.model_validate(data)
    assert restored.role == "thinking"
    assert restored.thinking == "Thinking content"


@pytest.mark.unit
def test_thinking_config() -> None:
    """Test thinking configuration."""

    # Test ThinkingConfig
    config = ThinkingConfig(enabled=True)
    assert config.enabled is True

    config2 = ThinkingConfig(enabled=False)
    assert config2.enabled is False

    # Test Settings has thinking_enabled field
    settings = Settings()
    assert hasattr(settings, "thinking_enabled")
    assert isinstance(settings.thinking_enabled, bool)


@pytest.mark.unit
def test_prompt_with_thinking() -> None:
    """Test prompt generation with thinking enabled."""

    # Create a mock context
    context_with_thinking = PromptContext(
        mode="chat",
        workspace_root=Path("/test"),
        tool_specs=[],
        thinking_enabled=True,
    )

    context_without_thinking = PromptContext(
        mode="chat",
        workspace_root=Path("/test"),
        tool_specs=[],
        thinking_enabled=False,
    )

    # Create a simple profile with thinking_format layer
    from ggbot.prompts.types import PromptProfile, PromptLayer

    profile = PromptProfile(
        name="test",
        layers=[
            PromptLayer(name="base", template="Base prompt"),
            PromptLayer(name="thinking_format", template="Thinking format instructions"),
        ]
    )

    # Test rendering
    builder = PromptBuilder()

    # With thinking enabled
    rendered_with = builder.render(profile=profile, context=context_with_thinking)
    assert "thinking_format" in rendered_with.layer_names
    assert "Thinking format instructions" in rendered_with.content

    # Without thinking enabled
    rendered_without = builder.render(profile=profile, context=context_without_thinking)
    assert "thinking_format" not in rendered_without.layer_names
    assert "Thinking format instructions" not in rendered_without.content


@pytest.mark.unit
def test_thinking_in_default_prompts() -> None:
    """Test that default prompts include thinking_format layer."""

    layers = _default_layers()
    layer_names = [layer.name for layer in layers]

    # Verify thinking_format layer exists
    assert "thinking_format" in layer_names

    # Find the thinking_format layer
    thinking_layer = next(layer for layer in layers if layer.name == "thinking_format")
    assert thinking_layer is not None
    assert "Thinking and Reasoning Format" in thinking_layer.template
    assert "思考：" in thinking_layer.template
    assert "Thinking:" in thinking_layer.template


@pytest.mark.unit
def test_thinking_event_in_transcript() -> None:
    """Test that thinking events can be recorded in transcript."""

    # This is a simple test to verify the thinking event structure
    # would be used in agent_loop.py
    thinking_event = {
        "ts_ms": 1234567890,
        "type": "thinking",
        "data": {
            "thinking": "This is a thinking process",
            "content_len": 27,
        }
    }

    # Verify structure
    assert thinking_event["type"] == "thinking"
    assert "thinking" in thinking_event["data"]
    assert "content_len" in thinking_event["data"]

    # Can be serialized to JSON
    json_str = json.dumps(thinking_event)
    loaded = json.loads(json_str)
    assert loaded["type"] == "thinking"
    assert loaded["data"]["thinking"] == "This is a thinking process"


if __name__ == "__main__":
    test_thinking_extraction()
    print("✓ test_thinking_extraction passed")

    test_chatmessage_with_thinking()
    print("✓ test_chatmessage_with_thinking passed")

    test_thinking_config()
    print("✓ test_thinking_config passed")

    test_prompt_with_thinking()
    print("✓ test_prompt_with_thinking passed")

    test_thinking_in_default_prompts()
    print("✓ test_thinking_in_default_prompts passed")

    test_thinking_event_in_transcript()
    print("✓ test_thinking_event_in_transcript passed")

    print("\nAll thinking tests passed!")
