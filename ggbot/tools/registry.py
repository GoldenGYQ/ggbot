from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass
from typing import Any, Callable, TypeVar, get_type_hints

from pydantic import BaseModel

from ..domain.types import ToolSpec
from .context import ToolContext


ToolHandler = Callable[[dict[str, Any], ToolContext | None], str]

F = TypeVar("F", bound=Callable[..., Any])


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

    def register_tool(self, fn: Any) -> None:
        reg = getattr(fn, "__ggbot_tool__", None)
        if reg is None:
            raise TypeError(f"Object is not a ggbot tool: {fn!r}")
        if not isinstance(reg, RegisteredTool):
            raise TypeError(f"Invalid __ggbot_tool__ payload on {fn!r}")
        self.register(reg.spec, reg.handler)

    def register_all(self, fns: list[Any] | tuple[Any, ...]) -> None:
        for fn in fns:
            self.register_tool(fn)

    def specs(self) -> list[ToolSpec]:
        return [t.spec for t in self._tools.values()]

    def openai_tools(self) -> list[dict[str, Any]]:
        return [spec.as_openai_tool() for spec in self.specs()]

    def call(self, name: str, arguments: dict[str, Any], *, ctx: ToolContext | None = None) -> str:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return self._tools[name].handler(arguments, ctx)


def _json_schema_from_pydantic(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    # OpenAI tool schema wants an object with properties + required
    return {
        "type": "object",
        "properties": schema.get("properties", {}),
        "required": schema.get("required", []),
        "additionalProperties": False,
    }


def _infer_description(func: Callable[..., Any]) -> str | None:
    doc = inspect.getdoc(func) or ""
    doc = doc.strip()
    if not doc:
        return None
    return doc.splitlines()[0].strip() or None


def _infer_input_model_from_signature(func: Callable[..., Any]) -> type[BaseModel] | None:
    sig = inspect.signature(func)

    if len(sig.parameters) == 1:
        args_param = next(iter(sig.parameters.values()))
    elif len(sig.parameters) == 2:
        args_param = list(sig.parameters.values())[1]
    else:
        raise TypeError("tool function must accept 1 argument (args) or 2 arguments (ctx, args)")

    param_name = args_param.name

    # Respect postponed evaluation of annotations (from __future__ import annotations)
    # by resolving the type hints. This also handles string annotations.
    try:
        hints = get_type_hints(func)
    except Exception:
        hints = {}

    ann = hints.get(param_name, args_param.annotation)
    if ann is inspect._empty:
        return None
    if isinstance(ann, type) and issubclass(ann, BaseModel):
        return ann
    return None


def _run_awaitable_sync(obj: Any) -> Any:
    if not inspect.isawaitable(obj):
        return obj

    async def _await() -> Any:
        return await obj

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_await())

    raise RuntimeError(
        "Async tool was invoked from a running event loop, but GGbot tool execution is sync. "
        "Run the query loop in a worker thread (like the TUI does) or add an async execution path."
    )


def tool(
    _func: F | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    input_model: type[BaseModel] | None = None,
) -> Callable[[F], F] | F:
    """Decorator (or decorator-factory) to register a tool.

    This supports two styles:

    1) Explicit metadata (old style, still supported):

       @tool(name="echo", description="echo", input_model=EchoArgs)
       def echo(args: EchoArgs) -> str: ...

    2) Inferred metadata (FastMCP-like ergonomics):

       @tool()
       def echo(args: EchoArgs) -> str:
           # Echo text.
           ...

       - name defaults to function name
       - description defaults to first line of docstring
       - input_model defaults to the single parameter annotation when it's a BaseModel subclass

    The decorated function can accept either:
    - (args: input_model) -> str | Any
    - (ctx: ToolContext, args: input_model) -> str | Any

    When using ToolContext, it is injected by the runtime and is NOT part of the
    model-facing tool schema.

    Tool results are coerced to str (JSON for non-strings).
    """

    def decorator(func: F) -> F:
        if not callable(func):
            raise TypeError("tool decorator expects a callable")

        nonlocal name, description, input_model

        sig = inspect.signature(func)
        if len(sig.parameters) not in {1, 2}:
            raise TypeError("tool function must accept 1 argument (args) or 2 arguments (ctx, args)")

        params = list(sig.parameters.values())
        ctx_param = params[0] if len(params) == 2 else None
        args_param = params[1] if len(params) == 2 else params[0]

        if ctx_param is not None:
            # Ensure the first arg is a ToolContext.
            try:
                hints = get_type_hints(func)
            except Exception:
                hints = {}
            resolved_ctx = hints.get(ctx_param.name, ctx_param.annotation)
            if resolved_ctx is inspect._empty or resolved_ctx is None:
                raise TypeError("Context parameter must be annotated as ToolContext")
            if resolved_ctx is not ToolContext:
                raise TypeError(
                    "When a tool declares two parameters, the first must be ToolContext"
                )

        if name is None:
            name = getattr(func, "__name__", None) or "tool"

        if description is None:
            description = _infer_description(func)

        if input_model is None:
            input_model = _infer_input_model_from_signature(func)

        if description is None or not str(description).strip():
            raise TypeError(
                "Tool description is required. Provide description=... or add a docstring."
            )
        if input_model is None:
            raise TypeError(
                "Tool input model is required. Provide input_model=... or annotate the single argument with a Pydantic BaseModel."
            )

        parameters = _json_schema_from_pydantic(input_model)
        spec = ToolSpec(name=str(name), description=str(description), parameters=parameters)

        try:
            hints = get_type_hints(func)
        except Exception:
            hints = {}
        resolved_arg_type = hints.get(args_param.name)

        def handler(arguments: dict[str, Any], ctx: ToolContext | None) -> str:
            assert input_model is not None
            parsed = input_model.model_validate(arguments)

            arg_type = resolved_arg_type or args_param.annotation
            if arg_type is dict or arg_type is Any:
                call_arg = parsed.model_dump()
            else:
                call_arg = parsed

            if ctx_param is None:
                result = func(call_arg)
            else:
                if ctx is None:
                    raise TypeError("ToolContext is required for this tool")
                result = func(ctx, call_arg)

            result = _run_awaitable_sync(result)

            if isinstance(result, str):
                return result
            return json.dumps(result, ensure_ascii=False)

        setattr(func, "__ggbot_tool__", RegisteredTool(spec=spec, handler=handler))
        return func

    # Support accidental @tool (no parens) in a helpful way.
    if _func is not None:
        # We allow it only when metadata can be inferred.
        return decorator(_func)

    return decorator


def collect_tools(module_or_obj: Any, registry: ToolRegistry) -> None:
    for _, member in inspect.getmembers(module_or_obj):
        reg = getattr(member, "__ggbot_tool__", None)
        if reg is not None:
            registry.register_tool(member)


def parse_tool_arguments(arguments_json: str) -> dict[str, Any]:
    # Some providers stream tool arguments as JSON fragments; after aggregation this should be valid JSON.
    if not arguments_json:
        return {}
    return json.loads(arguments_json)
