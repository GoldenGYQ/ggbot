"""API服务层 - 处理业务逻辑"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Callable

from ..core.agent_loop import ToolLimits, run_query
from ..core.domain import RuntimeEvent
from ..core.event_bus import EventSubscription, get_global_event_bus, subscribe_to_events
from ..core.runtime import (
    AgentRuntime,
    switch_runtime_session,
)
from ..core.runtime_events import consume_runtime_events
from ..core.sessions import default_sessions
from ..core.session_store import SessionStore
from ..core.transcript import Transcript
from ..core.types import ChatMessage
from ..tools.context import ToolContext

logger = logging.getLogger(__name__)


class APIService:
    """API服务 - 处理核心业务逻辑"""

    def __init__(self, runtime: AgentRuntime):
        self.runtime = runtime
        self.session_store = SessionStore.load(
            self.runtime.settings.resolved_transcript_dir()
        )
        self.active_queries: Dict[str, asyncio.Task] = {}
        self.event_buffer: List[Dict[str, Any]] = []
        self.max_event_buffer_size = 1000
        self._event_subscription: EventSubscription | None = subscribe_to_events(self._on_runtime_event)

    def _on_runtime_event(self, event: RuntimeEvent) -> None:
        """将运行时事件写入内存缓冲，供 /events 接口实时读取。"""
        self.add_event(
            {
                "type": event.type,
                "source": event.source,
                "timestamp": time.time(),
                "data": event.data,
            }
        )

    def close(self) -> None:
        """释放事件订阅，避免全局事件总线泄漏订阅对象。"""
        if self._event_subscription is not None:
            get_global_event_bus().unsubscribe(self._event_subscription)
            self._event_subscription = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            # 析构阶段不抛出异常，避免解释器关闭时出现噪音日志。
            pass

    # ==================== 会话管理 ====================

    async def list_sessions(self) -> Dict[str, Any]:
        """获取会话列表"""
        transcript_dir = self.runtime.settings.resolved_transcript_dir()
        defaults = default_sessions(
            workspace_root=self.runtime.settings.workspace_root,
            transcript_dir=transcript_dir
        )

        sessions = self.session_store.list_sessions(defaults)

        result = {
            "current_session_id": self.runtime.session_id,
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
            result["sessions"].append({
                "id": session_id,
                "title": meta.title if meta else "Untitled",
                "type": self._detect_session_type(session_id, defaults),
                "created_at": (meta.created_ms / 1000) if meta else 0,
                "updated_at": (meta.updated_ms / 1000) if meta else 0,
                "message_count": meta.user_turns if meta else 0,
                "user_turns": meta.user_turns if meta else 0,
                "is_current": session_id == self.runtime.session_id
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
        meta = self.session_store.metas.get(session_id)

        if not meta:
            raise ValueError(f"会话不存在: {session_id}")

        # 获取会话消息
        messages = []
        try:
            # 加载transcript获取消息
            transcript_path = self.session_store.transcript_dir / f"{session_id}.jsonl"
            if transcript_path.exists():
                transcript = Transcript(path=transcript_path)
                for event in transcript.iter_events():
                    if event.get("type") == "model_message":
                        msg_data = event.get("data", {})
                        messages.append({
                            "role": msg_data.get("role"),
                            "content": msg_data.get("content"),
                            "timestamp": event.get("ts_ms", 0)
                        })
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
            "messages": messages[-100:],  # 返回最近100条消息
            "metadata": {
                "title_gen_turn": meta.title_gen_turn,
                "created_ms": meta.created_ms,
                "updated_ms": meta.updated_ms,
            },
        }

    async def switch_session(self, session_id: str) -> Dict[str, Any]:
        """切换当前会话"""
        # 保存当前会话状态
        self.session_store.ensure_saved(self.runtime.session_id)
        previous_session_id = self.runtime.session_id

        # 切换到新会话
        loaded_count = switch_runtime_session(self.runtime, session_id=session_id)

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
        if session_id == self.runtime.session_id:
            raise ValueError("不能删除当前活动会话")

        # 删除会话文件
        existed = session_id in self.session_store.metas
        self.session_store.clear_session(session_id)

        return {
            "session_id": session_id,
            "deleted": existed,
            "message": "会话已删除" if existed else "会话不存在"
        }

    # ==================== 消息处理 ====================

    async def send_message(self, content: str, session_id: Optional[str] = None,
                          max_turns: Optional[int] = None,
                          thinking_enabled: Optional[bool] = None,
                          stream: bool = False) -> Dict[str, Any]:
        """发送消息并获取响应"""
        # 如果指定了会话ID，切换到该会话
        if session_id and session_id != self.runtime.session_id:
            await self.switch_session(session_id)

        # 请求级参数仅影响本次调用，避免污染全局 runtime 配置。
        effective_max_turns = self.runtime.settings.max_turns if max_turns is None else max_turns
        effective_thinking_enabled = (
            self.runtime.settings.thinking_enabled
            if thinking_enabled is None
            else thinking_enabled
        )

        # 准备工具上下文
        tool_context = ToolContext(
            session_id=self.runtime.session_id,
            transcript=self.runtime.transcript,
            workspace_root=self.runtime.settings.workspace_root,
        )

        # 创建事件收集器
        # 如果是流式模式，我们需要实时发送事件
        # 但在这个简化版本中，我们只是收集事件
        events_collector = EventsCollector()

        try:
            # 运行查询
            # run_query 是同步实现，放到线程中执行可避免阻塞 API 事件循环，
            # 同时兼容 async 工具（工具包装层会在无运行循环的线程内安全执行）。
            result = await asyncio.to_thread(
                run_query,
                client=self.runtime.client,
                registry=self.runtime.registry,
                transcript=self.runtime.transcript,
                messages=self.runtime.messages,
                user_text=content,
                max_turns=effective_max_turns,
                stream_printer=lambda delta: events_collector.add_assistant_delta(delta),
                tool_printer=lambda name, output: events_collector.add_tool_output(name, output),
                tool_context=tool_context,
                tool_limits=ToolLimits(
                    max_tool_calls=self.runtime.settings.max_tool_calls,
                    max_tool_calls_per_tool=self.runtime.settings.max_tool_calls_per_tool,
                    max_tool_calls_same_args=self.runtime.settings.max_tool_calls_same_args,
                ),
                thinking_enabled=effective_thinking_enabled,
            )

            # 处理运行时事件
            consume_runtime_events(
                result.events,
                on_turn_update=lambda data: events_collector.add_turn_update(data),
                on_turn_complete=lambda data: events_collector.add_turn_complete(data),
                on_provider_error=lambda data: events_collector.add_provider_error(data),
                on_thinking=lambda data: events_collector.add_thinking(data),
                on_assistant_delta=lambda data: events_collector.add_assistant_delta(data.get("delta", "")),
                on_assistant_final=lambda data: events_collector.add_assistant_final(data.get("content", "")),
            )

            # 更新会话统计
            turn_no = self.session_store.increment_user_turn(self.runtime.session_id)

            # 生成标题（如果是第一轮）
            title = None
            if turn_no == 1:
                title = await self._generate_title(content)
                if title:
                    self.session_store.set_title(self.runtime.session_id, title=title, title_gen_turn=turn_no)

            return {
                "success": True,
                "session_id": self.runtime.session_id,
                "turn_number": turn_no,
                "turns_used": result.turns_used,
                "title": title,
                "events": events_collector.get_events(),
                "final_response": events_collector.get_final_response(),
                "has_thinking": events_collector.has_thinking,
                "tool_calls": events_collector.tool_calls
            }

        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "session_id": self.runtime.session_id
            }

    async def _generate_title(self, seed: str) -> Optional[str]:
        """生成会话标题"""
        seed = (seed or "").strip()
        if not seed:
            return None

        prompt = (
            "Generate a short, human-friendly title for this conversation based on the user's message. "
            "Output ONLY the title. Keep it under 40 characters if possible."
        )

        try:
            final = self.runtime.client.complete(
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
        for spec in self.runtime.registry.specs():
            tools.append(
                {
                    "name": spec.name,
                    "description": spec.description or "",
                    "input_schema": spec.parameters,
                    # ToolSpec 层不暴露 requires_context，API 侧默认返回 False。
                    "requires_context": False,
                }
            )

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

        # 如果指定了会话ID，确保使用正确的会话
        if session_id != self.runtime.session_id:
            await self.switch_session(session_id)

        # 准备工具上下文
        tool_context = ToolContext(
            session_id=self.runtime.session_id,
            transcript=self.runtime.transcript,
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
                "session_id": self.runtime.session_id
            }

        except Exception as e:
            logger.error(f"执行工具失败: {e}")
            return {
                "success": False,
                "tool_name": name,
                "error": str(e),
                "session_id": self.runtime.session_id
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
            "session_id": self.runtime.session_id
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

    def add_assistant_delta(self, delta: str):
        """添加助手增量输出"""
        event_data = {
            "type": "assistant_delta",
            "timestamp": time.time(),
            "data": {"delta": delta}
        }
        self.events.append(event_data)
        self.final_response += delta

        # 实时发送事件
        if self.event_callback:
            self.event_callback(event_data)

    def add_assistant_final(self, content: str):
        """添加助手最终输出"""
        self.events.append({
            "type": "assistant_final",
            "timestamp": time.time(),
            "data": {"content": content}
        })

    def add_tool_output(self, name: str, output: str):
        """添加工具输出"""
        event_data = {
            "type": "tool_output",
            "timestamp": time.time(),
            "data": {"name": name, "output": output}
        }
        self.events.append(event_data)

        # 实时发送事件
        if self.event_callback:
            self.event_callback(event_data)

    def add_turn_update(self, data: Dict[str, Any]):
        """添加轮次更新"""
        self.events.append({
            "type": "turn_update",
            "timestamp": time.time(),
            "data": data
        })

    def add_turn_complete(self, data: Dict[str, Any]):
        """添加轮次完成"""
        self.events.append({
            "type": "turn_complete",
            "timestamp": time.time(),
            "data": data
        })

    def add_provider_error(self, data: Dict[str, Any]):
        """添加提供者错误"""
        self.events.append({
            "type": "provider_error",
            "timestamp": time.time(),
            "data": data
        })

    def add_thinking(self, data: Dict[str, Any]):
        """添加思考过程"""
        self.has_thinking = True
        event_data = {
            "type": "thinking",
            "timestamp": time.time(),
            "data": data
        }
        self.events.append(event_data)

        # 实时发送事件
        if self.event_callback:
            self.event_callback(event_data)

    def add_tool_call(self, name: str, arguments: Dict[str, Any]):
        """添加工具调用"""
        tool_call = {
            "name": name,
            "arguments": arguments,
            "timestamp": time.time()
        }
        self.tool_calls.append(tool_call)
        self.events.append({
            "type": "tool_call",
            "timestamp": time.time(),
            "data": tool_call
        })

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