from typing import Any

from pydantic import BaseModel, Field

from ggbot.tools.registry import ToolRegistry, tool


class EchoArgs(BaseModel):
    text: str = Field(..., min_length=1)


@tool(name="echo", description="echo", input_model=EchoArgs)
def echo(args: EchoArgs) -> str:
    return args.text


def test_tool_decorator_registers_and_validates() -> None:
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


def test_openai_tool_schema_shape() -> None:
    reg = ToolRegistry()
    decorated = getattr(echo, "__ggbot_tool__")
    reg.register(decorated.spec, decorated.handler)

    tools = reg.openai_tools()
    assert tools and tools[0]["type"] == "function"
    fn = tools[0]["function"]
    assert fn["name"] == "echo"
    assert fn["parameters"]["type"] == "object"
