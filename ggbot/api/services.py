"""API服务层 - 处理业务逻辑"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Callable

from ..runtime.agent_loop import ToolLimits, run_query
from ..models.runtime_models import RuntimeEvent
from ..app.app_bootstrap import AgentRuntime
from ..events.runtime_events import consume_runtime_events, runtime_event
from ..api.permission_manager import get_permission_manager
from .session_runtime_manager import SessionExecutionContext, SessionRuntimeManager
from ..state.sessions import default_sessions
from ..state.session_store import SessionStore
from ..state.transcript import Transcript
from ..models.protocol_models import ChatMessage
from ..tools.context import ToolContext
from ..providers.litellm_client import LiteLLMClient

logger = logging.getLogger(__name__)


class APIService:
    """API服务 - 处理核心业务逻辑"""

    def __init__(self, runtime: AgentRuntime):
        self.runtime = runtime
        self.session_store = SessionStore.load(
            self.runtime.settings.resolved_transcript_dir()
        )
        self.active_queries: Dict[str, asyncio.Task] = {}
        self._stop_signals: Dict[str, threading.Event] = {}
        self.event_buffer: List[Dict[str, Any]] = []
        self.max_event_buffer_size = 1000
        self.runtime_manager = SessionRuntimeManager(runtime)

    def close(self) -> None:
        """保留关闭接口，兼容现有调用方。"""
        return

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            # 析构阶段不抛出异常，避免解释器关闭时出现噪音日志。
            pass

    @property
    def current_session_id(self) -> str:
        return self.runtime_manager.current_session_id

    @current_session_id.setter
    def current_session_id(self, value: str) -> None:
        self.runtime_manager.current_session_id = value

    def _get_or_create_session_context(self, session_id: str) -> SessionExecutionContext:
        return self.runtime_manager.get_or_create_context(session_id)

    def _resolve_provider_client(self, provider_thinking: Optional[bool]) -> tuple[Any, str]:
        """Resolve per-request provider client without mutating global settings."""
        base_model = str(self.runtime.settings.openai_model or "").strip()
        if provider_thinking is None:
            return self.runtime.client, base_model

        provider_prefix = ""
        model_name = base_model
        if "/" in base_model:
            provider_prefix, model_name = base_model.split("/", 1)
            provider_prefix = provider_prefix.strip()
            model_name = model_name.strip()

        # Old DeepSeek dual-model mode:
        # deepseek-chat <-> deepseek-reasoner
        if model_name not in {"deepseek-chat", "deepseek-reasoner"}:
            return self.runtime.client, base_model

        target_name = "deepseek-reasoner" if provider_thinking else "deepseek-chat"
        if target_name == model_name:
            return self.runtime.client, base_model

        # LiteLLM may require provider-qualified model for DeepSeek aliases.
        # Prefer existing prefix; otherwise default to openai-compatible routing.
        prefix = provider_prefix or "openai"
        target_model = f"{prefix}/{target_name}"

        return (
            LiteLLMClient(
                model=target_model,
                api_base=self.runtime.settings.openai_base_url,
                api_key=self.runtime.settings.openai_api_key,
            ),
            target_model,
        )

    # ==================== 会话管理 ====================

    async def list_sessions(self) -> Dict[str, Any]:
        """获取会话列表"""
        transcript_dir = self.runtime.settings.resolved_transcript_dir()
        defaults = default_sessions(
            workspace_root=self.runtime.settings.workspace_root,
            transcript_dir=transcript_dir
        )

        sessions = self.session_store.list_sessions(defaults)
        default_ids = {defaults.chat, defaults.repl, defaults.tui}

        result = {
            "current_session_id": self.current_session_id,
            "default_sessions": {
                "chat": defaults.chat,
                "repl": defaults.repl,
                "tui": defaults.tui,
                "api": "api"  # API专用会话
            },
            "sessions": []
        }

        for session_id in sessions:
            meta = self.session_store.metas.get(session_id)
            # 隐藏空白默认会话，避免前端一上来出现 repl/chat/tui 三个占位项。
            if (
                session_id in default_ids
                and (meta is None or (meta.user_turns == 0 and not meta.title))
            ):
                continue
            result["sessions"].append({
                "id": session_id,
                "title": meta.title if meta else "Untitled",
                "type": self._detect_session_type(session_id, defaults),
                "created_at": (meta.created_ms / 1000) if meta else 0,
                "updated_at": (meta.updated_ms / 1000) if meta else 0,
                "message_count": meta.user_turns if meta else 0,
                "user_turns": meta.user_turns if meta else 0,
                "is_current": session_id == self.current_session_id
            })

        return result

    def _detect_session_type(self, session_id: str, defaults) -> str:
        """检测会话类型"""
        if session_id == defaults.chat:
            return "chat"
        elif session_id == defaults.repl:
            return "repl"
        elif session_id == defaults.tui:
            return "tui"
        elif session_id == "api":
            return "api"
        else:
            return "custom"

    async def create_session(self, session_type: str = "chat", title: Optional[str] = None) -> Dict[str, Any]:
        """创建新会话"""
        # 生成会话ID
        session_id = str(uuid.uuid4())

        # 创建会话元数据
        self.session_store.ensure_saved(session_id)

        if title:
            self.session_store.set_title(session_id, title=title, title_gen_turn=0)

        # 如果需要，可以在这里初始化会话的transcript

        return {
            "id": session_id,
            "title": title or "New Session",
            "type": session_type,
            "created_at": time.time(),
            "message_count": 0,
            "user_turns": 0
        }

    async def get_session(self, session_id: str) -> Dict[str, Any]:
        """获取会话详情"""
        # 如果元数据不存在但会话是默认类型，自动创建
        meta = self.session_store.metas.get(session_id)

        if not meta:
            defaults = default_sessions(
                workspace_root=self.runtime.settings.workspace_root,
                transcript_dir=self.runtime.settings.resolved_transcript_dir()
            )
            if session_id in (defaults.chat, defaults.repl, defaults.tui, "api"):
                meta = self.session_store.ensure_saved(session_id)
            else:
                raise ValueError(f"会话不存在: {session_id}")

        # 获取会话消息（回放 transcript 事件，保留结构化字段）
        messages: List[Dict[str, Any]] = []
        try:
            transcript_path = self.session_store.transcript_dir / f"{session_id}.jsonl"
            if transcript_path.exists():
                transcript = Transcript(path=transcript_path)
                messages = self._replay_transcript_messages(transcript)
        except Exception as e:
            logger.warning(f"加载会话消息失败: {e}")

        return {
            "id": session_id,
            "title": meta.title,
            "type": self._detect_session_type(session_id, default_sessions(
                workspace_root=self.runtime.settings.workspace_root,
                transcript_dir=self.runtime.settings.resolved_transcript_dir()
            )),
            "created_at": meta.created_ms / 1000,
            "updated_at": meta.updated_ms / 1000,
            "message_count": meta.user_turns,
            "user_turns": meta.user_turns,
            "messages": messages,
            "metadata": {
                "title_gen_turn": meta.title_gen_turn,
                "created_ms": meta.created_ms,
                "updated_ms": meta.updated_ms,
            },
        }

    async def get_session_model_io(self, session_id: str) -> Dict[str, Any]:
        """获取会话中模型实际输入/输出的原始消息（不做重放拼装）。"""
        meta = self.session_store.metas.get(session_id)
        if not meta:
            defaults = default_sessions(
                workspace_root=self.runtime.settings.workspace_root,
                transcript_dir=self.runtime.settings.resolved_transcript_dir()
            )
            if session_id in (defaults.chat, defaults.repl, defaults.tui, "api"):
                self.session_store.ensure_saved(session_id)
            else:
                raise ValueError(f"会话不存在: {session_id}")

        transcript_path = self.session_store.transcript_dir / f"{session_id}.jsonl"
        transcript = Transcript(path=transcript_path)
        model_io: List[Dict[str, Any]] = []

        for event in transcript.iter_events():
            if event.get("type") != "model_message":
                continue
            data = event.get("data") or {}
            role = str(data.get("role") or "")
            if not role:
                continue
            direction = "output" if role == "assistant" else "input"
            model_io.append(
                {
                    "ts_ms": int(event.get("ts_ms", 0) or 0),
                    "direction": direction,
                    "role": role,
                    "data": data,
                }
            )

        return {
            "session_id": session_id,
            "count": len(model_io),
            "items": model_io,
        }

    def _extract_plan_items(self, text: str) -> List[Dict[str, Any]]:
        if not text:
            return []
        match = re.search(r"<plan>(.*?)</plan>", text, re.DOTALL)
        if not match:
            return []
        lines = [line.strip() for line in match.group(1).splitlines() if line.strip()]
        plan: List[Dict[str, Any]] = []
        for line in lines:
            m = re.match(r"(?:\d+\.\s*)?\[(x| )\]\s*(.*?)(?:\s*\((.*?)\))?$", line)
            if m:
                plan.append(
                    {
                        "completed": m.group(1) == "x",
                        "text": m.group(2).strip(),
                        "tool": (m.group(3) or "").strip() or None,
                    }
                )
            else:
                plan.append({"completed": False, "text": line, "tool": None})
        return plan

    def _new_assistant_message(self, ts_ms: int) -> Dict[str, Any]:
        return {
            "role": "assistant",
            "content": "",
            "timestamp": ts_ms,
            "thinking": "",
            "plan": [],
            "tools": [],
            "status": "pending",
        }

    def _replay_transcript_messages(self, transcript: Transcript) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        current_assistant: Dict[str, Any] | None = None
        tool_by_id: Dict[str, Dict[str, Any]] = {}

        def start_new_assistant(ts_ms: int) -> Dict[str, Any]:
            nonlocal current_assistant
            current_assistant = self._new_assistant_message(ts_ms)
            messages.append(current_assistant)
            tool_by_id.clear()
            return current_assistant

        def ensure_assistant(ts_ms: int) -> Dict[str, Any]:
            nonlocal current_assistant
            if current_assistant is None:
                current_assistant = start_new_assistant(ts_ms)
            return current_assistant

        for event in transcript.iter_events():
            event_type = event.get("type")
            data = event.get("data") or {}
            ts_ms = int(event.get("ts_ms", 0) or 0)

            if event_type == "model_message":
                role = data.get("role")
                if role == "user":
                    current_assistant = None
                    tool_by_id.clear()
                    messages.append(
                        {
                            "role": "user",
                            "content": data.get("content", ""),
                            "timestamp": ts_ms,
                            "status": "done",
                        }
                    )
                    continue
                if role == "thinking":
                    assistant = ensure_assistant(ts_ms)
                    thinking = data.get("thinking") or data.get("content") or ""
                    assistant["thinking"] = (assistant.get("thinking") or "") + str(thinking)
                    continue
                if role == "assistant":
                    assistant = ensure_assistant(ts_ms)
                    next_content = data.get("content", "") or ""
                    prev_content = assistant.get("content") or ""
                    if next_content:
                        if not prev_content:
                            assistant["content"] = next_content
                        elif next_content != prev_content and next_content not in prev_content:
                            assistant["content"] = f"{prev_content}\n\n{next_content}"
                    plan = self._extract_plan_items(str(data.get("raw_content") or ""))
                    if plan:
                        assistant["plan"] = plan
                    assistant["status"] = "done"
                    continue
                if role == "tool":
                    assistant = ensure_assistant(ts_ms)
                    tool_call_id = data.get("tool_call_id")
                    tool = tool_by_id.get(tool_call_id or "")
                    if tool is None:
                        tool = {
                            "id": tool_call_id,
                            "name": data.get("name") or "tool",
                            "args": {},
                            "status": "done",
                        }
                        assistant["tools"].append(tool)
                        if tool_call_id:
                            tool_by_id[str(tool_call_id)] = tool
                    tool["result"] = data.get("content", "")
                    tool["status"] = "done"
                    continue

            if event_type == "turn_update":
                if messages and messages[-1].get("role") == "user" and current_assistant is None:
                    ensure_assistant(ts_ms)
                continue

            if event_type == "thinking":
                assistant = ensure_assistant(ts_ms)
                assistant["thinking"] = (assistant.get("thinking") or "") + str(data.get("thinking") or "")
                continue

            if event_type == "tool_call":
                assistant = ensure_assistant(ts_ms)
                has_pretool_content = bool((assistant.get("content") or "").strip())
                has_pretool_thinking = bool((assistant.get("thinking") or "").strip())
                has_pretool_plan = bool(assistant.get("plan"))
                has_tools = bool(assistant.get("tools"))
                if (has_pretool_content or has_pretool_thinking or has_pretool_plan) and not has_tools:
                    assistant["status"] = "done"
                    assistant = start_new_assistant(ts_ms)
                tool = {
                    "id": data.get("id"),
                    "name": data.get("name") or "tool",
                    "args": data.get("arguments") if isinstance(data.get("arguments"), dict) else {},
                    "status": "calling",
                }
                assistant["tools"].append(tool)
                if tool.get("id"):
                    tool_by_id[str(tool["id"])] = tool
                continue

            if event_type == "tool_result":
                assistant = ensure_assistant(ts_ms)
                tool_id = data.get("id")
                tool_name = data.get("name")
                target = tool_by_id.get(str(tool_id)) if tool_id else None
                if target is None and tool_name:
                    for t in reversed(assistant["tools"]):
                        if t.get("name") == tool_name and t.get("status") == "calling":
                            target = t
                            break
                if target is None:
                    target = {
                        "id": tool_id,
                        "name": tool_name or "tool",
                        "args": {},
                        "status": "done",
                    }
                    assistant["tools"].append(target)
                    if tool_id:
                        tool_by_id[str(tool_id)] = target
                target["status"] = "error" if data.get("error") else "done"
                if data.get("content") is not None:
                    target["result"] = data.get("content")
                continue

            if event_type == "turn_complete":
                if current_assistant is not None:
                    current_assistant["status"] = "done"
                current_assistant = None
                tool_by_id.clear()

        return messages

    async def switch_session(self, session_id: str) -> Dict[str, Any]:
        """切换当前会话"""
        self.session_store.ensure_saved(self.current_session_id)
        previous_session_id = self.current_session_id
        context = self._get_or_create_session_context(session_id)
        loaded_count = len(context.messages)
        self.current_session_id = session_id

        # 确保新会话的元数据存在
        self.session_store.ensure_saved(session_id)

        return {
            "previous_session_id": previous_session_id,
            "current_session_id": session_id,
            "messages_loaded": loaded_count,
            "session": await self.get_session(session_id)
        }

    async def update_session(self, session_id: str, title: Optional[str] = None) -> Dict[str, Any]:
        """更新会话"""
        if title:
            meta = self.session_store.metas.get(session_id)
            if meta:
                current_turn = meta.user_turns if meta else 0
                self.session_store.set_title(session_id, title=title, title_gen_turn=current_turn)

        return await self.get_session(session_id)

    async def delete_session(self, session_id: str) -> Dict[str, Any]:
        """删除会话"""
        if session_id == self.current_session_id:
            raise ValueError("不能删除当前活动会话")

        # 真正删除会话：移除元数据 + 删除 transcript 文件。
        meta_existed = session_id in self.session_store.metas
        if meta_existed:
            self.session_store.metas.pop(session_id, None)
            self.session_store.save()

        transcript_path = self.session_store.transcript_dir / f"{session_id}.jsonl"
        file_existed = transcript_path.exists()
        if file_existed:
            try:
                transcript_path.unlink()
            except OSError:
                logger.warning("删除会话文件失败: %s", transcript_path, exc_info=True)

        existed = meta_existed or file_existed
        self.runtime_manager.drop_context(session_id)

        return {
            "session_id": session_id,
            "deleted": existed,
            "message": "会话已删除" if existed else "会话不存在"
        }

    # ==================== 消息处理 ====================

    async def send_message(self, content: str, session_id: Optional[str] = None,
                          max_turns: Optional[int] = None,
                          thinking_enabled: Optional[bool] = None,
                          provider_thinking: Optional[bool] = None,
                          stream: bool = False,
                          event_callback: Optional[Callable[[RuntimeEvent], None]] = None,
                          connection_id: Optional[str] = None) -> Dict[str, Any]:
        """发送消息并获取响应"""
        target_session_id = session_id or self.current_session_id
        self.current_session_id = target_session_id
        self.session_store.ensure_saved(target_session_id)
        context = self._get_or_create_session_context(target_session_id)

        # 请求级参数仅影响本次调用，避免污染全局 runtime 配置。
        effective_max_turns = self.runtime.settings.max_turns if max_turns is None else max_turns
        effective_thinking_enabled = (
            self.runtime.settings.thinking_enabled
            if thinking_enabled is None
            else thinking_enabled
        )
        request_client, provider_model = self._resolve_provider_client(provider_thinking)
        temporary_client = request_client is not self.runtime.client
        stop_signal = threading.Event()
        self._stop_signals[target_session_id] = stop_signal

        # 准备工具上下文
        tool_context = ToolContext(
            session_id=target_session_id,
            transcript=context.transcript,
            workspace_root=self.runtime.settings.workspace_root,
        )
        # 创建事件收集器
        # 如果是流式模式，我们需要实时发送事件
        events_collector = EventsCollector()

        def combined_event_callback(event: RuntimeEvent):
            event_payload = {
                "type": event.type,
                "source": event.source,
                "timestamp": time.time(),
                "session_id": target_session_id,
                "data": event.data,
            }
            self.add_event(event_payload)

            # 1. 收集到 collector (为了最后的 result)
            consume_runtime_events(
                [event],
                on_turn_update=lambda data: events_collector.add_turn_update(data),
                on_turn_complete=lambda data: events_collector.add_turn_complete(data),
                on_provider_error=lambda data: events_collector.add_provider_error(data),
                on_thinking=lambda data: events_collector.add_thinking(data),
                on_assistant_delta=lambda data: events_collector.add_assistant_delta(data.get("delta", "")),
                on_assistant_final=lambda data: events_collector.add_assistant_final(data.get("content", "")),
                on_tool_call=lambda data: events_collector.add_tool_call_event(data),
                on_tool_result=lambda data: events_collector.add_tool_result(data),
                on_status=lambda data: events_collector.add_status(data),
                on_session_update=lambda data: events_collector.add_session_update(data),
                on_permission_request=lambda data: events_collector.add_permission_request(data),
                on_permission_response=lambda data: events_collector.add_permission_response(data),
            )
            # 2. 如果有外部回调，调用它
            if event_callback:
                enriched_data = dict(event.data or {})
                enriched_data["session_id"] = target_session_id
                event_callback(
                    RuntimeEvent(
                        type=event.type,
                        data=enriched_data,
                        source=event.source,
                    )
                )

        permission_manager = get_permission_manager()
        permission_ctx_token = permission_manager.set_request_context(
            connection_id=connection_id,
            session_id=target_session_id,
            user_id=None,
            event_callback=combined_event_callback,
            transcript=context.transcript,
        )

        try:
            async with self.runtime_manager.get_lock(target_session_id):
                result = await asyncio.to_thread(
                    run_query,
                    client=request_client,
                    registry=self.runtime.registry,
                    transcript=context.transcript,
                    messages=context.messages,
                    user_text=content,
                    max_turns=effective_max_turns,
                    stream_printer=None, # 我们现在用 event_callback 处理 delta
                    tool_printer=None, # 我们现在用 event_callback 处理 tool output
                    tool_context=tool_context,
                    tool_limits=ToolLimits(
                        max_tool_calls=self.runtime.settings.max_tool_calls,
                        max_tool_calls_per_tool=self.runtime.settings.max_tool_calls_per_tool,
                        max_tool_calls_same_args=self.runtime.settings.max_tool_calls_same_args,
                    ),
                    thinking_enabled=effective_thinking_enabled,
                    event_callback=combined_event_callback,
                    should_stop=stop_signal.is_set,
                )

            # 更新会话统计
            turn_no = self.session_store.increment_user_turn(target_session_id)

            # 生成标题（如果是第一轮）
            title = None
            current_meta = self.session_store.metas.get(target_session_id)
            should_generate_title = (
                turn_no == 1
                and (current_meta is None or not current_meta.title or current_meta.title == "Untitled")
            )
            if should_generate_title:
                title = await self._generate_title(content, client=request_client)
                if title:
                    self.session_store.set_title(target_session_id, title=title, title_gen_turn=turn_no)
                    combined_event_callback(
                        runtime_event(
                            "session_update",
                            {
                                "session_id": target_session_id,
                                "title": title,
                                "user_turns": turn_no,
                            },
                        )
                    )

            return {
                "success": True,
                "session_id": target_session_id,
                "turn_number": turn_no,
                "turns_used": result.turns_used,
                "title": title,
                "provider_model": provider_model,
                "provider_thinking": provider_thinking,
                "events": events_collector.get_events(),
                "final_response": events_collector.get_final_response(),
                "has_thinking": events_collector.has_thinking,
                "tool_calls": events_collector.tool_calls
            }

        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            raise
        finally:
            if temporary_client:
                try:
                    request_client.close()
                except Exception:
                    pass
            permission_manager.reset_request_context(permission_ctx_token)
            current_signal = self._stop_signals.get(target_session_id)
            if current_signal is stop_signal:
                self._stop_signals.pop(target_session_id, None)

    async def stop_message(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """请求中断某个会话的当前生成任务。"""
        target_session_id = session_id or self.current_session_id
        stop_signal = self._stop_signals.get(target_session_id)
        if stop_signal is None:
            return {
                "success": False,
                "session_id": target_session_id,
                "stopped": False,
                "message": "当前会话没有正在运行的生成任务。",
            }
        stop_signal.set()
        return {
            "success": True,
            "session_id": target_session_id,
            "stopped": True,
            "message": "已请求中断当前生成任务。",
        }

    async def _generate_title(self, seed: str, client: Any | None = None) -> Optional[str]:
        """生成会话标题"""
        seed = (seed or "").strip()
        if not seed:
            return None

        prompt = (
            "Generate a short, human-friendly title for this conversation based on the user's message. "
            "Output ONLY the title. Keep it under 40 characters if possible."
        )

        try:
            final = (client or self.runtime.client).complete(
                messages=[
                    ChatMessage(role="system", content=prompt),
                    ChatMessage(role="user", content=seed),
                ],
                tools=None,
            )
            title = (final.content or "").strip()
            # 只取第一行
            title = title.splitlines()[0].strip() if title else ""
            if not title:
                # 回退方案：截取种子文本
                title = " ".join(seed.split())
                title = title[:40] + ("..." if len(title) > 40 else "")
            return title
        except Exception as e:
            logger.warning(f"生成标题失败: {e}")
            return None

    # ==================== 工具管理 ====================

    async def list_tools(self) -> Dict[str, Any]:
        """获取可用工具列表"""
        tools = []
        specs = []
        if hasattr(self.runtime.registry, "specs"):
            try:
                specs = list(self.runtime.registry.specs())
            except Exception:
                specs = []

        for spec in specs:
            tools.append(
                {
                    "name": spec.name,
                    "description": spec.description or "",
                    "input_schema": spec.parameters,
                    # ToolSpec 层不暴露 requires_context，API 侧默认返回 False。
                    "requires_context": False,
                }
            )

        # 兼容旧风格 registry mock（tests 使用 list_tools/get_tool）。
        if not tools and hasattr(self.runtime.registry, "list_tools"):
            try:
                registry_any = self.runtime.registry  # 兼容测试桩上的动态属性
                for name in getattr(registry_any, "list_tools")():
                    tool_obj = getattr(registry_any, "get_tool")(name)
                    tools.append(
                        {
                            "name": name,
                            "description": getattr(tool_obj, "description", "") or "",
                            "input_schema": {},
                            "requires_context": bool(getattr(tool_obj, "requires_context", False)),
                        }
                    )
            except Exception:
                pass

        return {
            "total": len(tools),
            "tools": tools
        }

    async def execute_tool(self, name: str, arguments: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        """执行工具"""
        # 验证工具是否存在
        tool_names = {spec.name for spec in self.runtime.registry.specs()}

        if name not in tool_names:
            raise ValueError(f"工具不存在: {name}")

        target_session_id = session_id or self.current_session_id
        self.current_session_id = target_session_id
        self.session_store.ensure_saved(target_session_id)
        context = self._get_or_create_session_context(target_session_id)

        # 准备工具上下文
        tool_context = ToolContext(
            session_id=target_session_id,
            transcript=context.transcript,
            workspace_root=self.runtime.settings.workspace_root,
        )

        try:
            # 通过线程执行同步的 ToolRegistry.call，避免阻塞事件循环。
            # 这同样支持 async 工具：其 awaitable 会在线程内被安全收敛为最终字符串结果。
            result = await asyncio.to_thread(
                self.runtime.registry.call,
                name,
                arguments,
                ctx=tool_context,
            )

            return {
                "success": True,
                "tool_name": name,
                "result": result,
                "session_id": target_session_id
            }

        except Exception as e:
            logger.error(f"执行工具失败: {e}")
            return {
                "success": False,
                "tool_name": name,
                "error": str(e),
                "session_id": target_session_id
            }

    async def respond_permission(
        self,
        request_id: str,
        allowed: bool,
        reason: str = "",
        actor_connection_id: str | None = None,
        actor_session_id: str | None = None,
    ) -> Dict[str, Any]:
        """Handle frontend permission decision for pending tool requests."""
        accepted = get_permission_manager().resolve(
            request_id=request_id,
            allowed=allowed,
            reason=reason,
            actor_connection_id=actor_connection_id,
            actor_session_id=actor_session_id,
            actor_user_id=None,
        )
        return {
            "success": accepted,
            "request_id": request_id,
            "allowed": allowed,
            "reason": reason,
            "message": "Permission decision accepted" if accepted else "Permission request not found or already resolved",
        }

    # ==================== 配置管理 ====================

    async def get_config(self) -> Dict[str, Any]:
        """获取当前配置"""
        settings = self.runtime.settings

        # 安全地获取配置，不暴露敏感信息
        config = {
            "openai_model": settings.openai_model,
            "openai_base_url": settings.openai_base_url,
            "workspace_root": str(settings.workspace_root),
            "max_turns": settings.max_turns,
            "max_tool_calls": settings.max_tool_calls,
            "max_tool_calls_per_tool": settings.max_tool_calls_per_tool,
            "max_tool_calls_same_args": settings.max_tool_calls_same_args,
            "thinking_enabled": settings.thinking_enabled,
            "shell_confirm": settings.shell_confirm,
            "transcript_dir": str(settings.resolved_transcript_dir()),
            "session_id": self.current_session_id
        }

        # 检查API密钥是否存在（但不暴露值）
        config["has_openai_api_key"] = bool(settings.openai_api_key)

        return config

    async def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """更新配置"""
        settings = self.runtime.settings

        # 应用更新
        for key, value in updates.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
            else:
                logger.warning(f"忽略未知配置项: {key}")

        return await self.get_config()

    # ==================== 事件管理 ====================

    async def get_recent_events(self, limit: int = 100) -> Dict[str, Any]:
        """获取最近事件"""
        # 从事件缓冲区获取
        events = self.event_buffer[-limit:] if self.event_buffer else []

        return {
            "total": len(self.event_buffer),
            "limit": limit,
            "events": events
        }

    def add_event(self, event: Dict[str, Any]):
        """添加事件到缓冲区"""
        self.event_buffer.append(event)
        # 限制缓冲区大小
        if len(self.event_buffer) > self.max_event_buffer_size:
            self.event_buffer = self.event_buffer[-self.max_event_buffer_size:]


class EventsCollector:
    """事件收集器 - 收集查询过程中产生的事件"""

    def __init__(self, event_callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.events: List[Dict[str, Any]] = []
        self.final_response: str = ""
        self.has_thinking: bool = False
        self.tool_calls: List[Dict[str, Any]] = []
        self.event_callback = event_callback  # 实时事件回调

    def _append_event(
        self,
        event_type: str,
        data: Dict[str, Any],
        *,
        aliases: Optional[List[str]] = None,
        realtime: bool = False,
    ) -> None:
        event_data = {
            "type": event_type,
            "timestamp": time.time(),
            "data": data,
        }
        self.events.append(event_data)

        if aliases:
            for alias in aliases:
                self.events.append(
                    {
                        "type": alias,
                        "timestamp": event_data["timestamp"],
                        "data": data,
                    }
                )

        if realtime and self.event_callback:
            self.event_callback(event_data)

    def add_assistant_delta(self, delta: str):
        """添加助手增量输出"""
        self._append_event("assistant_delta", {"delta": delta}, realtime=True)
        self.final_response += delta

    def add_assistant_final(self, content: str):
        """添加助手最终输出"""
        self._append_event("assistant_final", {"content": content})

    def add_tool_output(self, name: str, output: str):
        """添加工具输出。"""
        self._append_event(
            "tool_result",
            {
                "name": name,
                "content": output,
                "error": False,
            },
            realtime=True,
        )

    def add_turn_update(self, data: Dict[str, Any]):
        """添加轮次更新"""
        self._append_event("turn_update", data, realtime=True)

    def add_turn_complete(self, data: Dict[str, Any]):
        """添加轮次完成"""
        self._append_event("turn_complete", data)

    def add_error(self, data: Dict[str, Any]):
        """添加错误事件（兼容旧版 provider_error 事件）。"""
        self._append_event("error", data, aliases=["provider_error"])

    def add_provider_error(self, data: Dict[str, Any]):
        """添加提供者错误（向后兼容入口）。"""
        self.add_error(data)

    def add_thinking(self, data: Dict[str, Any]):
        """添加思考过程"""
        self.has_thinking = True
        self._append_event("thinking", data, realtime=True)

    def add_tool_result(self, data: Dict[str, Any]):
        """添加运行时工具结果事件。"""
        self._append_event("tool_result", data, realtime=True)

    def add_status(self, data: Dict[str, Any]):
        """添加状态事件。"""
        self._append_event("status", data, realtime=True)

    def add_session_update(self, data: Dict[str, Any]):
        """添加会话更新事件。"""
        self._append_event("session_update", data)

    def add_permission_request(self, data: Dict[str, Any]):
        """添加权限请求事件。"""
        self._append_event("permission_request", data)

    def add_permission_response(self, data: Dict[str, Any]):
        """添加权限响应事件。"""
        self._append_event("permission_response", data)

    def add_tool_call(self, name: str, arguments: Dict[str, Any]):
        """添加工具调用（旧接口）。"""
        tool_call = {
            "name": name,
            "arguments": arguments,
            "timestamp": time.time()
        }
        self.tool_calls.append(tool_call)
        self._append_event("tool_call", tool_call, realtime=True)

    def add_tool_call_event(self, data: Dict[str, Any]):
        """添加运行时工具调用事件。"""
        tool_call = {
            "id": data.get("id"),
            "name": data.get("name", "unknown"),
            "arguments": data.get("arguments") if isinstance(data.get("arguments"), dict) else {},
            "timestamp": time.time(),
        }
        self.tool_calls.append(tool_call)
        self._append_event("tool_call", data, realtime=True)

    def get_events(self) -> List[Dict[str, Any]]:
        """获取所有事件"""
        return self.events

    def get_final_response(self) -> str:
        """获取最终响应"""
        return self.final_response


# 全局API服务实例
_global_api_service: Optional[APIService] = None


def get_global_api_service(runtime: Optional[AgentRuntime] = None) -> APIService:
    """获取全局API服务"""
    global _global_api_service
    if runtime is not None:
        _global_api_service = APIService(runtime)
    if _global_api_service is None:
        raise RuntimeError("APIService is not initialized")
    return _global_api_service


def create_api_service(runtime: AgentRuntime) -> APIService:
    """创建新的API服务"""
    return APIService(runtime)
