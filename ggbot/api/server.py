"""FastAPI服务器实现"""

from __future__ import annotations

import asyncio
import functools
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, Awaitable

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from ..runtime.agent_loop import ToolLimits
from ..models.runtime_models import RuntimeEvent, SessionState
from ..app.app_bootstrap import AgentRuntime
from ..state.session_store import SessionStore
from ..state.transcript import Transcript
from ..models.protocol_models import ChatMessage
from ..workspace.permissions import ensure_under_root, PermissionError as WorkspacePermissionError

from .services import APIService, get_global_api_service

# 模块级 logger - 只创建，不配置任何 handler
logger = logging.getLogger(__name__)


STREAMABLE_EVENT_TYPES = {
    "assistant_delta",
    "assistant_final",
    "provider_chunk",
    "thinking",
    "plan_update",
    "tool_call",
    "tool_result",
    "turn_update",
    "turn_complete",
    "status",
    "error",
    "provider_error",  # backward-compatible alias
    "session_update",
    "permission_request",
    "permission_response",
}


# ==================== 数据模型 ====================

class MessageRequest(BaseModel):
    """发送消息请求"""
    content: str
    session_id: Optional[str] = None
    max_turns: Optional[int] = None
    thinking_enabled: Optional[bool] = None
    stream: Optional[bool] = False


class ToolExecuteRequest(BaseModel):
    """执行工具请求"""
    name: str
    arguments: Dict[str, Any]
    session_id: str


class SessionCreateRequest(BaseModel):
    """创建会话请求"""
    type: str = "chat"
    title: Optional[str] = None
    workspace_root: Optional[str] = None


class SessionUpdateRequest(BaseModel):
    """更新会话请求"""
    title: Optional[str] = None


class ConfigUpdateRequest(BaseModel):
    """更新配置请求"""
    openai_model: Optional[str] = None
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None
    workspace_root: Optional[str] = None
    max_turns: Optional[int] = None
    max_tool_calls: Optional[int] = None
    max_tool_calls_per_tool: Optional[int] = None
    max_tool_calls_same_args: Optional[int] = None
    thinking_enabled: Optional[bool] = None
    skills_enabled: Optional[bool] = None
    skills_dir: Optional[str] = None
    shell_confirm: Optional[bool] = None


class PermissionResponseRequest(BaseModel):
    """权限响应请求"""
    request_id: str
    allowed: bool
    reason: Optional[str] = None
    session_id: Optional[str] = None


class WebSocketMessage(BaseModel):
    """WebSocket消息"""
    type: str
    id: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)
    payload: Optional[Dict[str, Any]] = None


class DocumentChangeSetRequest(BaseModel):
    """构建文档改动集请求"""
    before: str = ""
    after: str = ""
    document_id: Optional[str] = None
    source: Optional[str] = None


class DocxManifestBuildRequest(BaseModel):
    """根据 markdown 文档块构建 docx 清单请求"""
    markdown_text: str
    docs_dir: str = "docs"
    manifest_name: str = "doc_build_manifest.json"
    docx_path: str = "docs/output.docx"
    write_files: bool = True


class DocxBuildRunRequest(BaseModel):
    """执行 docx 构建步骤请求"""
    manifest_path: str = "docs/doc_build_manifest.json"
    session_id: Optional[str] = None
    only_section_id: Optional[str] = None
    resume: bool = True
    write_state: bool = True
    state_path: Optional[str] = None


# ==================== 异常日志装饰器 ====================

def log_exceptions(logger: logging.Logger, reraise: bool = True):
    """统一异常日志装饰器"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                # HTTPException 直接抛出，不需要记录
                raise
            except Exception as e:
                logger.exception(f"{func.__name__} 失败: {type(e).__name__}")
                if reraise:
                    raise
                return {"success": False, "error": str(e)}
        return wrapper
    return decorator


# ==================== WebSocket连接管理器 ====================

class ConnectionManager:
    """WebSocket连接管理器"""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self._connection_count_log_threshold = 10  # 每10个连接记录一次

    async def connect(self, websocket: WebSocket, connection_id: str):
        """连接WebSocket"""
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        
        count = len(self.active_connections)
        # 高频操作用 debug
        logger.debug(f"WebSocket连接: {connection_id}, 活跃连接数: {count}")
        
        # 关键状态变化用 info（每10个连接记录一次）
        if count % self._connection_count_log_threshold == 0:
            logger.info(f"WebSocket活跃连接数: {count}")

    def disconnect(self, connection_id: str):
        """断开WebSocket连接"""
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]

        count = len(self.active_connections)
        logger.debug(f"WebSocket断开: {connection_id}, 剩余连接: {count}")

    async def send_message(self, connection_id: str, message: Dict[str, Any]):
        """发送消息到指定连接"""
        if connection_id in self.active_connections:
            try:
                await self.active_connections[connection_id].send_json(message)
            except Exception as e:
                logger.error(f"发送消息到连接 {connection_id} 失败", exc_info=True)
                self.disconnect(connection_id)

    async def broadcast(self, message: Dict[str, Any]):
        """广播消息到所有连接"""
        disconnected = []
        for connection_id, websocket in self.active_connections.items():
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"广播消息到连接 {connection_id} 失败", exc_info=True)
                disconnected.append(connection_id)

        for connection_id in disconnected:
            self.disconnect(connection_id)


# ==================== API服务器 ====================

class APIServer:
    """GGbot API服务器"""

    def __init__(
        self, 
        runtime: AgentRuntime, 
        host: str = "127.0.0.1", 
        port: int = 8000,
        logger: Optional[logging.Logger] = None
    ):
        if runtime is None:
            raise ValueError("runtime cannot be None")
        
        self.runtime = runtime
        self.host = host
        self.port = port
        self.connection_manager = ConnectionManager()
        self.api_service = get_global_api_service(runtime)
        self.logger = logger or logging.getLogger(f"{__name__}.APIServer")

        # 创建FastAPI应用
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            await self._on_startup()
            yield
            await self._on_shutdown()

        self.app = FastAPI(
            title="GGbot API",
            description="GGbot的WebSocket和REST API接口",
            version="0.1.0",
            lifespan=lifespan
        )

        # 添加CORS中间件
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # 设置路由
        self._setup_routes()

    async def _on_startup(self):
        """服务器启动时的钩子"""
        self.logger.info("API服务器启动中...")
        self.logger.info(f"监听地址: {self.host}:{self.port}")
        self.logger.info(f"会话ID: {self.runtime.session_id}")
        # 可以在这里添加更多初始化逻辑

    async def _on_shutdown(self):
        """服务器关闭时的钩子"""
        self.logger.info("API服务器关闭中...")
        # 可以在这里添加清理逻辑

    def _setup_routes(self):
        """设置API路由"""

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            connection_id = str(uuid.uuid4())
            await self._handle_websocket(websocket, connection_id)

        @self.app.get("/")
        async def root():
            return {
                "name": "GGbot API",
                "version": "0.1.0",
                "status": "running"
            }

        @self.app.get("/api/v1/health")
        async def health_check():
            return {
                "status": "healthy", 
                "timestamp": time.time(),
                "connections": len(self.connection_manager.active_connections)
            }

        @self.app.options("/api/v1/health")
        async def health_check_options():
            response = JSONResponse({"ok": True})
            response.headers["access-control-allow-origin"] = "*"
            response.headers["access-control-allow-methods"] = "*"
            response.headers["access-control-allow-headers"] = "*"
            return response

        # DEPRECATED (Transport split): HTTP message send endpoint is disabled.
        # Realtime message lifecycle is WS-only via `send_message` command.
        # Legacy code kept for reference (do not delete):
        # @self.app.post("/api/v1/messages")
        # async def send_message(request: MessageRequest):
        #     stream = request.stream if hasattr(request, 'stream') else False
        #     if stream:
        #         return StreamingResponse(
        #             self._stream_send_message(request),
        #             media_type="application/x-ndjson"
        #         )
        #     else:
        #         return await self._handle_send_message(request)

        @self.app.get("/api/v1/sessions")
        async def list_sessions():
            return await self._handle_list_sessions()

        @self.app.post("/api/v1/sessions")
        async def create_session(request: SessionCreateRequest):
            return await self._handle_create_session(request)

        @self.app.get("/api/v1/sessions/{session_id}")
        async def get_session(session_id: str):
            return await self._handle_get_session(session_id)

        @self.app.get("/api/v1/sessions/{session_id}/model-io")
        async def get_session_model_io(session_id: str):
            return await self._handle_get_session_model_io(session_id)

        @self.app.put("/api/v1/sessions/{session_id}")
        async def update_session(session_id: str, request: SessionUpdateRequest):
            return await self._handle_update_session(session_id, request)

        @self.app.delete("/api/v1/sessions/{session_id}")
        async def delete_session(session_id: str):
            return await self._handle_delete_session(session_id)

        @self.app.get("/api/v1/tools")
        async def list_tools():
            return await self._handle_list_tools()

        @self.app.post("/api/v1/tools/execute")
        async def execute_tool(request: ToolExecuteRequest):
            return await self._handle_execute_tool(request)

        @self.app.get("/api/v1/config")
        async def get_config():
            return await self._handle_get_config()

        @self.app.put("/api/v1/config")
        async def update_config(request: ConfigUpdateRequest):
            return await self._handle_update_config(request)

        @self.app.get("/api/v1/events")
        async def get_recent_events(limit: int = 100):
            return await self._handle_get_recent_events(limit)

        @self.app.post("/api/v1/documents/change-set")
        async def build_document_change_set(request: DocumentChangeSetRequest):
            return await self._handle_build_document_change_set(request)

        @self.app.post("/api/v1/documents/docx-manifest")
        async def build_docx_manifest(request: DocxManifestBuildRequest):
            return await self._handle_build_docx_manifest(request)

        @self.app.post("/api/v1/documents/docx-build/run")
        async def run_docx_build(request: DocxBuildRunRequest):
            return await self._handle_run_docx_build(request)

        @self.app.get("/api/v1/workspace/file")
        async def get_workspace_file(path: str = Query(..., description="工作区相对路径")):
            workspace_root = Path(self.runtime.settings.workspace_root).resolve()
            try:
                target = ensure_under_root(workspace_root, (workspace_root / path))
            except WorkspacePermissionError as exc:
                raise HTTPException(status_code=403, detail=str(exc)) from exc

            if not target.exists() or not target.is_file():
                raise HTTPException(status_code=404, detail=f"文件不存在: {path}")
            if target.suffix.lower() != ".docx":
                raise HTTPException(status_code=400, detail="当前接口仅支持 .docx 文件预览")

            return FileResponse(
                path=str(target),
                filename=target.name,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        # DEPRECATED (Transport split): HTTP permission response endpoint is disabled.
        # Permission decisions must go through WS `permission_response` command.
        # Legacy code kept for reference (do not delete):
        # @self.app.post("/api/v1/permissions/respond")
        # async def respond_permission(request: PermissionResponseRequest):
        #     return await self._handle_permission_response(request)

    async def _handle_websocket(self, websocket: WebSocket, connection_id: str):
        """处理WebSocket连接"""
        await self.connection_manager.connect(websocket, connection_id)
        event_loop = asyncio.get_running_loop()

        try:
            while True:
                try:
                    data = await websocket.receive_json()
                    await self._handle_client_message(connection_id, data, event_loop=event_loop)
                except WebSocketDisconnect:
                    break
                except RuntimeError as e:
                    message = str(e)
                    # Starlette 在连接已关闭后调用 receive_json 会抛该异常；
                    # 这里应结束循环，避免重复报错刷屏。
                    if "WebSocket is not connected" in message:
                        logger.debug(f"WebSocket连接已关闭: {connection_id}")
                        break
                    logger.error("处理WebSocket消息失败", exc_info=True)
                    await self._send_error(connection_id, message)
                except Exception as e:
                    logger.error(f"处理WebSocket消息失败", exc_info=True)
                    await self._send_error(connection_id, str(e))

        except Exception as e:
            logger.error(f"WebSocket连接处理失败", exc_info=True)
        finally:
            self.connection_manager.disconnect(connection_id)

    def _schedule_event_delivery(self, loop: asyncio.AbstractEventLoop, connection_id: str, event: RuntimeEvent) -> None:
        """Schedule websocket delivery on the websocket loop from any thread."""
        try:
            loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self._send_event_to_connection(connection_id, event))
            )
        except RuntimeError:
            # Loop may already be closed during shutdown; dropping late events is acceptable.
            self.logger.debug("WebSocket event dropped because event loop is not available")

    async def _send_event_to_connection(self, connection_id: str, event: RuntimeEvent):
        """发送事件到指定连接"""
        message = {
            "type": "event",
            "event_type": event.type,
            "data": event.data,
            "timestamp": time.time(),
            "source": event.source
        }
        await self.connection_manager.send_message(connection_id, message)

    async def _handle_client_message(
        self,
        connection_id: str,
        data: Dict[str, Any],
        *,
        event_loop: asyncio.AbstractEventLoop | None = None,
    ):
        """处理客户端消息"""
        try:
            message_type = data.get("type")

            if message_type == "command":
                command = data.get("command")
                payload = data.get("payload", {})
                message_id = data.get("id", str(uuid.uuid4()))

                if not isinstance(command, str):
                    raise ValueError("命令必须是字符串")
                # Do not block receive loop on long-running commands (e.g. send_message),
                # otherwise follow-up commands like permission_response cannot be handled in time.
                asyncio.create_task(
                    self._process_command_and_reply(
                        connection_id=connection_id,
                        message_id=message_id,
                        command=command,
                        payload=payload,
                        event_loop=event_loop,
                    )
                )
            else:
                logger.warning(f"未知的消息类型: {message_type}")
                await self._send_error(connection_id, f"未知的消息类型: {message_type}")

        except Exception as e:
            logger.error(f"处理客户端消息失败", exc_info=True)
            await self._send_error(connection_id, str(e))

    async def _process_command_and_reply(
        self,
        *,
        connection_id: str,
        message_id: str,
        command: str,
        payload: Dict[str, Any],
        event_loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        try:
            response = await self._handle_command(
                command,
                payload,
                connection_id=connection_id,
                event_loop=event_loop,
            )
            await self.connection_manager.send_message(
                connection_id,
                {
                    "type": "response",
                    "id": message_id,
                    "command": command,
                    "payload": response,
                    "timestamp": time.time(),
                },
            )
        except Exception as e:
            logger.error(f"处理命令失败: command={command}", exc_info=True)
            await self._send_error(connection_id, str(e))

    async def _send_error(self, connection_id: str, error_message: str):
        """发送错误消息"""
        await self.connection_manager.send_message(connection_id, {
            "type": "error",
            "message": error_message,
            "timestamp": time.time()
        })

    @log_exceptions(logger)
    async def _handle_command(
        self,
        command: str,
        payload: Dict[str, Any],
        *,
        connection_id: str | None = None,
        event_loop: asyncio.AbstractEventLoop | None = None,
    ) -> Dict[str, Any]:
        """处理命令"""
        if command == "send_message":
            content = payload.get("content", "")
            session_id = payload.get("session_id")
            max_turns = payload.get("max_turns")
            thinking_enabled = payload.get("thinking_enabled")
            provider_thinking = payload.get("provider_thinking")
            if thinking_enabled is not None and not isinstance(thinking_enabled, bool):
                raise ValueError("thinking_enabled必须是布尔值")
            if provider_thinking is not None and not isinstance(provider_thinking, bool):
                raise ValueError("provider_thinking必须是布尔值")
            ws_event_callback: Callable[[RuntimeEvent], None] | None = None
            if connection_id and event_loop is not None:
                # Bind runtime events to the initiating websocket connection.
                def ws_event_callback(event: RuntimeEvent) -> None:
                    self._schedule_event_delivery(event_loop, connection_id, event)

            return await self.api_service.send_message(
                content,
                session_id,
                max_turns,
                thinking_enabled,
                provider_thinking=provider_thinking,
                event_callback=ws_event_callback,
                connection_id=connection_id,
            )
        elif command == "stop_message":
            session_id = payload.get("session_id")
            return await self.api_service.stop_message(session_id)
        elif command == "list_sessions":
            return await self.api_service.list_sessions()
        elif command == "get_session":
            session_id = payload.get("session_id")
            if not session_id:
                raise ValueError("缺少session_id参数")
            return await self.api_service.get_session(session_id)
        elif command == "switch_session":
            session_id = payload.get("session_id")
            if not session_id:
                raise ValueError("缺少session_id参数")
            return await self.api_service.switch_session(session_id)
        elif command == "list_tools":
            return await self.api_service.list_tools()
        elif command == "execute_tool":
            name = payload.get("name")
            arguments = payload.get("arguments", {})
            session_id = payload.get("session_id", self.runtime.session_id)
            if not name:
                raise ValueError("缺少name参数")
            return await self.api_service.execute_tool(name, arguments, session_id)
        elif command == "get_config":
            return await self.api_service.get_config()
        elif command == "update_config":
            updates = payload.get("updates", {})
            return await self.api_service.update_config(updates)
        elif command == "get_recent_events":
            limit = payload.get("limit", 100)
            return await self.api_service.get_recent_events(limit)
        elif command == "permission_response":
            request_id = payload.get("request_id")
            allowed = payload.get("allowed")
            reason = payload.get("reason", "")
            session_id = payload.get("session_id")
            if not request_id:
                raise ValueError("缺少request_id参数")
            if not isinstance(allowed, bool):
                raise ValueError("allowed必须是布尔值")
            if not session_id:
                raise ValueError("缺少session_id参数")
            return await self.api_service.respond_permission(
                request_id=request_id,
                allowed=allowed,
                reason=str(reason or ""),
                actor_connection_id=connection_id,
                actor_session_id=str(session_id),
            )
        elif command == "build_document_change_set":
            return await self.api_service.build_document_change_set(
                before=str(payload.get("before") or ""),
                after=str(payload.get("after") or ""),
                document_id=(
                    str(payload.get("document_id"))
                    if payload.get("document_id") is not None
                    else None
                ),
                source=(str(payload.get("source")) if payload.get("source") is not None else None),
            )
        elif command == "build_docx_manifest":
            return await self.api_service.build_docx_manifest(
                markdown_text=str(payload.get("markdown_text") or ""),
                docs_dir=str(payload.get("docs_dir") or "docs"),
                manifest_name=str(payload.get("manifest_name") or "doc_build_manifest.json"),
                docx_path=str(payload.get("docx_path") or "docs/output.docx"),
                write_files=bool(payload.get("write_files", True)),
            )
        elif command == "run_docx_build":
            return await self.api_service.run_docx_build(
                manifest_path=str(payload.get("manifest_path") or "docs/doc_build_manifest.json"),
                session_id=(str(payload.get("session_id")) if payload.get("session_id") is not None else None),
                only_section_id=(str(payload.get("only_section_id")) if payload.get("only_section_id") is not None else None),
                resume=bool(payload.get("resume", True)),
                write_state=bool(payload.get("write_state", True)),
                state_path=(str(payload.get("state_path")) if payload.get("state_path") is not None else None),
            )
        else:
            raise ValueError(f"未知命令: {command}")

    @log_exceptions(logger)
    async def _handle_send_message(self, request: MessageRequest) -> Dict[str, Any]:
        """处理发送消息请求"""
        # 业务操作使用 info 级别
        content_preview = request.content[:100] + "..." if len(request.content) > 100 else request.content
        logger.info(f"发送消息: session={request.session_id}, content_len={len(request.content)}, stream={request.stream}")
        
        result = await self.api_service.send_message(
            content=request.content,
            session_id=request.session_id,
            max_turns=request.max_turns,
            thinking_enabled=request.thinking_enabled
        )
        
        logger.info(f"消息处理完成: session={request.session_id}, turns_used={result.get('turns_used')}")
        
        if isinstance(result, dict) and result.get("success") is False:
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
        return result

    async def _stream_send_message(self, request: MessageRequest):
        """流式发送消息"""
        queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def event_callback(event: RuntimeEvent):
            loop.call_soon_threadsafe(queue.put_nowait, event)

        logger.info(f"开始流式响应: session={request.session_id}")

        send_task = asyncio.create_task(
            self.api_service.send_message(
                content=request.content,
                session_id=request.session_id,
                max_turns=request.max_turns,
                thinking_enabled=request.thinking_enabled,
                stream=True,
                event_callback=event_callback
            )
        )

        try:
            while not send_task.done() or not queue.empty():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.2)
                    
                    if event.type in STREAMABLE_EVENT_TYPES:
                        yield json.dumps({
                            "type": "event",
                            "event_type": event.type,
                            "data": event.data,
                            "timestamp": time.time()
                        }) + "\n"
                except asyncio.TimeoutError:
                    continue

            result = await send_task

            yield json.dumps({
                "type": "complete",
                "data": {
                    "session_id": result.get("session_id"),
                    "turn_number": result.get("turn_number"),
                    "turns_used": result.get("turns_used"),
                    "title": result.get("title"),
                    "final_response": result.get("final_response", ""),
                    "success": True
                }
            }) + "\n"
            
            logger.info(f"流式响应完成: session={request.session_id}")

        except Exception as e:
            logger.error(f"流式发送消息失败", exc_info=True)
            yield json.dumps({
                "type": "error",
                "data": {"error": str(e)}
            }) + "\n"
        finally:
            if not send_task.done():
                send_task.cancel()

    @log_exceptions(logger)
    async def _handle_list_sessions(self) -> Dict[str, Any]:
        """处理获取会话列表请求"""
        return await self.api_service.list_sessions()

    @log_exceptions(logger)
    async def _handle_create_session(self, request: SessionCreateRequest) -> Dict[str, Any]:
        """处理创建会话请求"""
        logger.info(f"创建会话: type={request.type}, title={request.title}")
        result = await self.api_service.create_session(
            session_type=request.type,
            title=request.title
        )
        logger.info(f"会话创建成功: session_id={result.get('session_id')}")
        return result

    @log_exceptions(logger)
    async def _handle_get_session(self, session_id: str) -> Dict[str, Any]:
        """处理获取会话详情请求"""
        try:
            return await self.api_service.get_session(session_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @log_exceptions(logger)
    async def _handle_get_session_model_io(self, session_id: str) -> Dict[str, Any]:
        """处理获取会话模型原始输入输出请求"""
        try:
            return await self.api_service.get_session_model_io(session_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @log_exceptions(logger)
    async def _handle_update_session(self, session_id: str, request: SessionUpdateRequest) -> Dict[str, Any]:
        """处理更新会话请求"""
        try:
            return await self.api_service.update_session(
                session_id=session_id,
                title=request.title
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @log_exceptions(logger)
    async def _handle_delete_session(self, session_id: str) -> Dict[str, Any]:
        """处理删除会话请求"""
        logger.info(f"删除会话: {session_id}")
        try:
            result = await self.api_service.delete_session(session_id)
            logger.info(f"会话删除成功: {session_id}")
            return result
        except ValueError as e:
            logger.warning(f"删除会话参数错误: {e}")
            raise HTTPException(status_code=400, detail=str(e))

    @log_exceptions(logger)
    async def _handle_list_tools(self) -> Dict[str, Any]:
        """处理获取工具列表请求"""
        return await self.api_service.list_tools()

    @log_exceptions(logger)
    async def _handle_execute_tool(self, request: ToolExecuteRequest) -> Dict[str, Any]:
        """处理执行工具请求"""
        logger.debug(f"执行工具: name={request.name}, session={request.session_id}")
        try:
            result = await self.api_service.execute_tool(
                name=request.name,
                arguments=request.arguments,
                session_id=request.session_id
            )
            logger.debug(f"工具执行完成: {request.name}, success={result.get('success')}")
            return result
        except ValueError as e:
            logger.warning(f"工具执行参数错误: {e}")
            raise HTTPException(status_code=400, detail=str(e))

    @log_exceptions(logger)
    async def _handle_get_config(self) -> Dict[str, Any]:
        """处理获取配置请求"""
        return await self.api_service.get_config()

    @log_exceptions(logger)
    async def _handle_update_config(self, request: ConfigUpdateRequest) -> Dict[str, Any]:
        """处理更新配置请求"""
        updates = {}
        for field in request.model_fields_set:
            value = getattr(request, field)
            if value is not None:
                updates[field] = value
        
        # 敏感信息脱敏记录
        log_updates = updates.copy()
        if 'openai_api_key' in log_updates and log_updates['openai_api_key']:
            log_updates['openai_api_key'] = '***' + log_updates['openai_api_key'][-4:]
        
        logger.info(f"更新配置: {list(updates.keys())}")
        result = await self.api_service.update_config(updates)
        logger.info("配置更新成功")
        return result

    @log_exceptions(logger)
    async def _handle_get_recent_events(self, limit: int) -> Dict[str, Any]:
        """处理获取最近事件请求"""
        return await self.api_service.get_recent_events(limit)

    @log_exceptions(logger)
    async def _handle_build_document_change_set(
        self, request: DocumentChangeSetRequest
    ) -> Dict[str, Any]:
        """处理构建文档改动集请求"""
        return await self.api_service.build_document_change_set(
            before=request.before,
            after=request.after,
            document_id=request.document_id,
            source=request.source,
        )

    @log_exceptions(logger)
    async def _handle_build_docx_manifest(
        self, request: DocxManifestBuildRequest
    ) -> Dict[str, Any]:
        """处理构建 docx 文档清单请求"""
        return await self.api_service.build_docx_manifest(
            markdown_text=request.markdown_text,
            docs_dir=request.docs_dir,
            manifest_name=request.manifest_name,
            docx_path=request.docx_path,
            write_files=request.write_files,
        )

    @log_exceptions(logger)
    async def _handle_run_docx_build(
        self, request: DocxBuildRunRequest
    ) -> Dict[str, Any]:
        """处理执行 docx 构建步骤请求"""
        return await self.api_service.run_docx_build(
            manifest_path=request.manifest_path,
            session_id=request.session_id,
            only_section_id=request.only_section_id,
            resume=request.resume,
            write_state=request.write_state,
            state_path=request.state_path,
        )

    @log_exceptions(logger)
    async def _handle_permission_response(self, request: PermissionResponseRequest) -> Dict[str, Any]:
        """处理权限响应请求"""
        if not request.session_id:
            raise HTTPException(status_code=400, detail="缺少session_id参数")
        result = await self.api_service.respond_permission(
            request_id=request.request_id,
            allowed=request.allowed,
            reason=request.reason or "",
            actor_connection_id=None,
            actor_session_id=request.session_id,
        )
        if result.get("success") is not True:
            raise HTTPException(status_code=404, detail=result.get("message", "Permission request not found"))
        return result

    def run(self):
        """运行API服务器"""
        import uvicorn
        
        # 让 uvicorn 管理日志，不覆盖其配置
        uvicorn.run(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info",
            access_log=True
        )


# ==================== 工厂函数 ====================

def create_api_server(
    runtime: AgentRuntime, 
    host: str = "127.0.0.1", 
    port: int = 8000,
    logger: Optional[logging.Logger] = None
) -> APIServer:
    """创建API服务器实例"""
    return APIServer(runtime, host, port, logger)


def run_api_server(
    runtime: AgentRuntime, 
    host: str = "127.0.0.1", 
    port: int = 8000,
    logger: Optional[logging.Logger] = None
):
    """运行API服务器"""
    server = create_api_server(runtime, host, port, logger)
    server.run()
