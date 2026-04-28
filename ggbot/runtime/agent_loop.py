'''
智能循环类，用于执行智能体的循环。
每个循环包含一个查询、一个模型调用、一个工具调用、一个响应。
'''
from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import contextvars
import json
import threading

from ..providers.types import ChatCompletionClient
from ..tools.context import ToolContext
from ..tools.registry import ToolRegistry, parse_tool_arguments
from ..transport.transcript_contract import TranscriptEventType
from .history_repair import auto_heal_missing_tool_messages, sanitize_orphan_tool_messages
from .model_interaction import extract_thinking_content, perform_model_turn
from ..models.runtime_models import RuntimeEvent
from ..events.runtime_events import runtime_event
from .tool_execution import execute_tool_call
from ..state.transcript import Transcript
from ..models.protocol_models import ChatMessage


'''
查询结果数据类，用于存储查询结果信息。
'''
@dataclass
class QueryResult:
    messages: list[ChatMessage]
    turns_used: int = 0
    events: list[RuntimeEvent] = field(default_factory=list)


'''
工具调用限制数据类，定义了智能体在一次循环中可以调用的工具的各种限制参数。
'''
@dataclass
class ToolLimits:
    max_tool_calls: int = 30
    max_tool_calls_per_tool: int = 12
    max_tool_calls_same_args: int = 3


'''
工具调用预算状态类，用于管理工具调用预算状态。
'''
@dataclass
class _ToolBudgetState:
    limits: ToolLimits
    total: int = 0
    per_tool: dict[str, int] = None  # type: ignore[assignment]
    per_tool_args: dict[tuple[str, str], int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.per_tool is None:
            self.per_tool = {}
        if self.per_tool_args is None:
            self.per_tool_args = {}

    def check_and_record(self, *, name: str, args: dict) -> str | None:
        ''' 检查工具调用预算是否超限'''
        self.total += 1
        if self.total > self.limits.max_tool_calls:
            return f"Tool budget exceeded: max_tool_calls={self.limits.max_tool_calls}"

        self.per_tool[name] = self.per_tool.get(name, 0) + 1
        if self.per_tool[name] > self.limits.max_tool_calls_per_tool:
            return (
                "Tool budget exceeded: "
                f"tool={name} max_per_tool={self.limits.max_tool_calls_per_tool}"
            )

        args_key = json.dumps(args, ensure_ascii=False, sort_keys=True)
        k = (name, args_key)
        self.per_tool_args[k] = self.per_tool_args.get(k, 0) + 1
        if self.per_tool_args[k] > self.limits.max_tool_calls_same_args:
            return (
                "Tool budget exceeded: "
                f"tool={name} max_same_args={self.limits.max_tool_calls_same_args}"
            )

        return None



'''
运行智能体循环。
'''
def run_query(
    *,
    client: ChatCompletionClient,
    registry: ToolRegistry,
    transcript: Transcript,
    messages: list[ChatMessage],
    user_text: str,
    max_turns: int,
    stream_printer: Callable[[str], None] | None = None,
    tool_printer: Callable[[str, str], None] | None = None,
    tool_context: ToolContext | None = None,
    tool_limits: ToolLimits | None = None,
    thinking_enabled: bool = False,
    event_callback: Callable[[RuntimeEvent], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    request_system_message: str | None = None,
) -> QueryResult:
    """执行一轮带工具调用能力的对话主循环。

    该函数会在 `max_turns` 上限内重复执行：
    1) 调用模型生成回复（可能包含 tool_calls）；
    2) 若有工具调用则执行工具并把结果回灌到消息历史；
    3) 持续写入 transcript 并产出 RuntimeEvent。

    Args:
        client: 模型客户端，负责流式推理与最终收集（provider 适配层）。
        registry: 工具注册表，提供 tool schema 与实际工具执行入口。
        transcript: 当前会话的持久化日志（jsonl）；函数会原地追加事件。
        messages: 当前会话消息历史（含 system/user/assistant/tool）；函数会原地修改。
        user_text: 本轮用户输入文本。
        max_turns: 本次查询最多允许的模型轮次，防止无限循环。
        stream_printer: 文本增量回调；收到模型 delta 时即时输出（CLI/TUI 常用）。
        tool_printer: 工具输出回调；每次工具执行后用于打印工具结果（可选）。
        tool_context: 传给工具的运行时上下文（session/transcript/workspace 等），
            不属于模型可见参数，仅在工具执行阶段使用。
        tool_limits: 工具调用预算配置（总次数/单工具次数/同参重复次数上限）；
            为空时使用默认预算。
        thinking_enabled: 是否启用 thinking 内容提取与事件输出。
        event_callback: 运行时事件实时回调（turn_update/tool_call/tool_result 等）；
            用于 WS 推送或 UI 实时渲染。
        should_stop: 外部中断检查回调；返回 True 时尽快终止当前查询。

    Returns:
        QueryResult:
            - messages: 本轮执行后的消息列表（与传入 messages 为同一对象语义）。
            - turns_used: 实际消耗的模型轮次数。
            - events: 本次执行聚合的 RuntimeEvent 快照。

    Notes:
        - 本函数会原地修改 `messages` 与 `transcript`（有副作用）。
        - `event_callback` 是实时通道，`events` 是调用结束后的聚合结果。
        - 工具执行失败/预算超限会转为可观察事件与 transcript 记录，而非直接中断进程。
    """
    runtime_events: list[RuntimeEvent] = []

    def add_event(event: RuntimeEvent):
        runtime_events.append(event)
        if event_callback:
            event_callback(event)

    def is_interrupted() -> bool:
        return bool(should_stop is not None and should_stop())

    if request_system_message and request_system_message.strip():
        messages.append(ChatMessage(role="system", content=request_system_message.strip()))
        transcript.append("model_message", messages[-1].model_dump(exclude_none=True))

    messages.append(ChatMessage(role="user", content=user_text))
    transcript.append("model_message", messages[-1].model_dump(exclude_none=True))

    tools = registry.openai_tools()

    turns = 0
    budget = _ToolBudgetState(tool_limits or ToolLimits())
    tool_state_lock = threading.Lock()

    # 记录轮次信息到转录
    transcript.append("turn_info", {
        "max_turns": max_turns,
        "start_turn": 0,
    })

    while turns < max_turns:
        if is_interrupted():
            interrupt_payload = {"message": "Generation interrupted by user request."}
            transcript.append("status", interrupt_payload)
            add_event(runtime_event("status", interrupt_payload))
            break
        turns += 1

        # 记录当前轮次到转录
        transcript.append("turn_update", {
            "current_turn": turns,
            "max_turns": max_turns,
        })
        add_event(runtime_event("turn_update", {"current_turn": turns, "max_turns": max_turns}))

        #修复缺失的工具调用消息
        sanitize_orphan_tool_messages(messages=messages)
        auto_heal_missing_tool_messages(messages=messages)
        # 执行模型轮次
        turn_outcome = perform_model_turn(
            client=client,
            messages=messages,
            transcript=transcript,
            tools=tools,
            stream_printer=stream_printer,
            thinking_enabled=thinking_enabled,
            event_callback=add_event,
            should_stop=is_interrupted,
        )

        if turn_outcome.should_stop:
            break

        '''
        执行工具调用。
        '''
        interrupted_during_tools = False
        tool_calls = turn_outcome.tool_calls
        if tool_calls:
            max_workers = max(1, min(len(tool_calls), 8))
            # 线程并发执行工具调用
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []
                for tool_call in tool_calls:
                    if is_interrupted():
                        interrupt_payload = {"message": "Tool execution interrupted by user request."}
                        transcript.append("status", interrupt_payload)
                        add_event(runtime_event("status", interrupt_payload))
                        interrupted_during_tools = True
                        break

                    raw_arguments = tool_call.function.arguments or ""
                    parsed_arguments: dict | None = None
                    parse_error: str | None = None
                    try:
                        parsed_arguments = parse_tool_arguments(raw_arguments)
                    except Exception as e:
                        parse_error = f"{type(e).__name__}: {e}"

                    tool_call_payload = {
                        "id": tool_call.id,
                        "name": tool_call.function.name,
                        "arguments": parsed_arguments,
                        "raw_arguments": raw_arguments,
                    }
                    if parse_error is not None:
                        tool_call_payload["parse_error"] = parse_error
                    add_event(runtime_event("tool_call", tool_call_payload))

                    futures.append(
                        executor.submit(
                            contextvars.copy_context().run,
                            execute_tool_call,
                            tool_call=tool_call,
                            registry=registry,
                            transcript=transcript,
                            messages=messages,
                            tool_printer=tool_printer,
                            tool_context=tool_context,
                            budget=budget,
                            emit_tool_call_event=False,
                            interrupt_callback=is_interrupted,
                            state_lock=tool_state_lock,
                        )
                    )

                for future in as_completed(futures):
                    tool_outcome = future.result()
                    for event in tool_outcome.events:
                        add_event(event)
        if interrupted_during_tools:
            break
        
        '''
        记录最终轮次信息到转录    
        检查最后一个助手消息是否有工具调用    
        '''
    last_has_tool_calls = False
    for msg in reversed(messages):
        if msg.role == "assistant":
            last_has_tool_calls = bool(msg.tool_calls)
            break
        '''
        记录最终轮次信息到转录    
        检查最后一个助手消息是否有工具调用    
        '''

    transcript.append("turn_complete", {
        "turns_used": turns,
        "max_turns": max_turns,
        "completed": turns < max_turns or not last_has_tool_calls,
    })
    add_event(
        runtime_event(
            "turn_complete",
            {
                "turns_used": turns,
                "max_turns": max_turns,
                "completed": turns < max_turns or not last_has_tool_calls,
            },
        )
    )

    return QueryResult(messages=messages, turns_used=turns, events=runtime_events)

