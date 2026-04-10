from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel

from ..core.types import ToolSpec


ToolHandler = Callable[[dict[str, Any]], str]


@dataclass(frozen=True)
class RegisteredTool:
    spec: ToolSpec
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, spec: ToolSpec, handler: ToolHandler) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = RegisteredTool(spec=spec, handler=handler)

    def specs(self) -> list[ToolSpec]:
        return [t.spec for t in self._tools.values()]

    def openai_tools(self) -> list[dict[str, Any]]:
        return [spec.as_openai_tool() for spec in self.specs()]

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return self._tools[name].handler(arguments)


def _json_schema_from_pydantic(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    # OpenAI tool schema wants an object with properties + required
    return {
        "type": "object",
        "properties": schema.get("properties", {}),
        "required": schema.get("required", []),
        "additionalProperties": False,
    }


def tool(*, name: str, description: str, input_model: type[BaseModel]):
    """Decorator to register a tool from a function.

    The decorated function can accept either:
    - (args: input_model) -> str
    - (args: dict) -> str
    """

    def decorator(func: Callable[..., str]):
        if not callable(func):
            raise TypeError("tool decorator expects a callable")

        sig = inspect.signature(func)
        if len(sig.parameters) != 1:
            raise TypeError("tool function must accept exactly one argument")

        parameters = _json_schema_from_pydantic(input_model)
        spec = ToolSpec(name=name, description=description, parameters=parameters)

        def handler(arguments: dict[str, Any]) -> str:
            parsed = input_model.model_validate(arguments)
            first_param = next(iter(sig.parameters.values()))
            if first_param.annotation is dict or first_param.annotation is Any:
                return func(parsed.model_dump())
            return func(parsed)

        func.__ggbot_tool__ = RegisteredTool(spec=spec, handler=handler)  # type: ignore[attr-defined]
        return func

    return decorator


def collect_tools(module_or_obj: Any, registry: ToolRegistry) -> None:
    for _, member in inspect.getmembers(module_or_obj):
        reg = getattr(member, "__ggbot_tool__", None)
        if reg is not None:
            registry.register(reg.spec, reg.handler)


def parse_tool_arguments(arguments_json: str) -> dict[str, Any]:
    # Some providers stream tool arguments as JSON fragments; after aggregation this should be valid JSON.
    if not arguments_json:
        return {}
    return json.loads(arguments_json)
