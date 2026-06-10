"""Tests for ToolRegistry: registration, schema generation, context injection, and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, Field

from ggbot.state.transcript import Transcript
from ggbot.tools.context import ToolContext
from ggbot.tools.registry import ToolRegistry, tool


class EchoArgs(BaseModel):
    text: str = Field(..., min_length=1)


@tool(name="echo", description="echo", input_model=EchoArgs)
def echo(args: EchoArgs) -> str:
    return args.text


@tool()
def echo_inferred(args: EchoArgs) -> str:
    """echo inferred"""
    return args.text


@pytest.mark.unit
def test_tool_decorator_registers_and_validates() -> None:
    """A tool registered via @tool decorator should validate inputs and execute correctly."""
    reg = ToolRegistry()
    decorated = getattr(echo, "__ggbot_tool__")
    reg.register(decorated.spec, decorated.handler)

    assert reg.call("echo", {"text": "hi"}) == "hi"

    # invalid: min_length
    try:
        reg.call("echo", {"text": ""})
        assert False, "expected validation error"
    except Exception:
        pass


@pytest.mark.unit
def test_tool_decorator_infers_name_description_and_model() -> None:
    """A tool without explicit name/description should infer them from the function."""
    reg = ToolRegistry()
    reg.register_tool(echo_inferred)

    assert reg.call("echo_inferred", {"text": "hi"}) == "hi"

    tools = reg.openai_tools()
    fn_names = {t["function"]["name"] for t in tools}
    assert "echo_inferred" in fn_names


@pytest.mark.unit
def test_openai_tool_schema_shape() -> None:
    """The generated OpenAI-compatible tool schema should have the correct structure."""
    reg = ToolRegistry()
    decorated = getattr(echo, "__ggbot_tool__")
    reg.register(decorated.spec, decorated.handler)

    tools = reg.openai_tools()
    assert tools and tools[0]["type"] == "function"
    fn = tools[0]["function"]
    assert fn["name"] == "echo"
    assert fn["parameters"]["type"] == "object"


@tool()
def echo_with_ctx(ctx: ToolContext, args: EchoArgs) -> str:
    """echo with ctx"""
    return f"{ctx.session_id}:{args.text}"


@pytest.mark.unit
def test_tool_registry_supports_context_injection(tmp_path: Path) -> None:
    """Tools that accept a ToolContext should have it injected automatically."""
    reg = ToolRegistry()
    reg.register_tool(echo_with_ctx)

    transcript = Transcript(path=tmp_path / "t.jsonl")
    ctx = ToolContext(session_id="s1", transcript=transcript, workspace_root=tmp_path)

    assert reg.call("echo_with_ctx", {"text": "hi"}, ctx=ctx) == "s1:hi"

    try:
        reg.call("echo_with_ctx", {"text": "hi"})
        assert False, "expected missing ctx error"
    except TypeError:
        pass

