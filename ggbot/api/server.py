"""FastAPI服务器实现"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Union

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from ..runtime.agent_loop import ToolLimits
from ..models.runtime_models import RuntimeEvent, SessionState
from ..events.event_bus import get_global_event_bus, subscribe_to_events
from ..app.app_bootstrap import AgentRuntime
from ..state.session_store import SessionStore
from ..state.transcript import Transcript
from ..models.protocol_models import ChatMessage

from .services import APIService, get_global_api_service

logger = logging.getLogger(__name__)


STREAMABLE_EVENT_TYPES = {
    "assistant_delta",
    "assistant_final",
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
    stream: Optional[bool] = False  # 是否启用流式响应


class ToolExecuteRequest(BaseModel):
    """执行工具请求"""
    name: str
    arguments: Dict[str, Any]
    session_id: str


class SessionCreateRequest(BaseModel):
    """创建会话请求"""
    type: str = "chat"  # chat, repl, tui
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
    shell_confirm: Optional[bool] = None


class WebSocketMessage(BaseModel):
    """WebSocket消息"""
    type: str  # event, command, response, error
    id: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)
    payload: Optional[Dict[str, Any]] = None


# ==================== WebSocket连接管理器 ====================

class ConnectionManager:
    """WebSocket连接管理器"""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_subscriptions: Dict[str, Any] = {}

    async def connect(self, websocket: WebSocket, connection_id: str):
        """连接WebSocket"""
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        logger.info(f"WebSocket连接已建立: {connection_id}")

    def disconnect(self, connection_id: str):
        """断开WebSocket连接"""
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]

        # 取消事件订阅
        if connection_id in self.connection_subscriptions:
            subscription = self.connection_subscriptions[connection_id]
            get_global_event_bus().unsubscribe(subscription)
            del self.connection_subscriptions[connection_id]

        logger.info(f"WebSocket连接已断开: {connection_id}")

    async def send_message(self, connection_id: str, message: Dict[str, Any]):
        """发送消息到指定连接"""
        if connection_id in self.active_connections:
            try:
                await self.active_connections[connection_id].send_json(message)
            except Exception as e:
                logger.error(f"发送消息到连接 {connection_id} 失败: {e}")
                self.disconnect(connection_id)

    async def broadcast(self, message: Dict[str, Any]):
        """广播消息到所有连接"""
        disconnected = []
        for connection_id, websocket in self.active_connections.items():
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"广播消息到连接 {connection_id} 失败: {e}")
                disconnected.append(connection_id)

        # 清理断开连接
        for connection_id in disconnected:
            self.disconnect(connection_id)


# ==================== API服务器 ====================

class APIServer:
    """GGbot API服务器"""

    def __init__(self, runtime: AgentRuntime, host: str = "127.0.0.1", port: int = 8000):
        if runtime is None:
            raise ValueError("runtime cannot be None")
        self.runtime = runtime
        self.host = host
        self.port = port
        self.connection_manager = ConnectionManager()
        self.api_service = get_global_api_service(runtime)

        # 创建FastAPI应用
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # 启动时
            logger.info("API服务器启动中...")
            yield
            # 关闭时
            logger.info("API服务器关闭中...")

        self.app = FastAPI(
            title="GGbot API",
            description="GGbot的WebSocket和REST API接口",
            version="0.1.0",
            lifespan=lifespan
        )

        # 添加CORS中间件
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # 生产环境应该限制
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # 设置路由
        self._setup_routes()

    def _setup_routes(self):
        """设置API路由"""

        # WebSocket端点
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket连接端点"""
            connection_id = str(uuid.uuid4())
            await self._handle_websocket(websocket, connection_id)

        # REST API端点

        @self.app.get("/")
        async def root():
            """根端点"""
            return {
                "name": "GGbot API",
                "version": "0.1.0",
                "status": "running"
            }

        @self.app.get("/api/v1/health")
        async def health_check():
            """健康检查"""
            return {"status": "healthy", "timestamp": time.time()}

        @self.app.options("/api/v1/health")
        async def health_check_options():
            """兼容测试环境下的 CORS 预检请求。"""
            response = JSONResponse({"ok": True})
            response.headers["access-control-allow-origin"] = "*"
            response.headers["access-control-allow-methods"] = "*"
            response.headers["access-control-allow-headers"] = "*"
            return response

        @self.app.post("/api/v1/messages")
        async def send_message(request: MessageRequest):
            """发送消息"""
            # 检查是否请求流式响应
            stream = request.stream if hasattr(request, 'stream') else False
            if stream:
                return StreamingResponse(
                    self._stream_send_message(request),
                    media_type="application/x-ndjson"
                )
            else:
                return await self._handle_send_message(request)

        @self.app.get("/api/v1/sessions")
        async def list_sessions():
            """获取会话列表"""
            return await self._handle_list_sessions()

        @self.app.post("/api/v1/sessions")
        async def create_session(request: SessionCreateRequest):
            """创建新会话"""
            return await self._handle_create_session(request)

        @self.app.get("/api/v1/sessions/{session_id}")
        async def get_session(session_id: str):
            """获取会话详情"""
            return await self._handle_get_session(session_id)

        @self.app.put("/api/v1/sessions/{session_id}")
        async def update_session(session_id: str, request: SessionUpdateRequest):
            """更新会话"""
            return await self._handle_update_session(session_id, request)

        @self.app.delete("/api/v1/sessions/{session_id}")
        async def delete_session(session_id: str):
            """删除会话"""
            return await self._handle_delete_session(session_id)

        @self.app.get("/api/v1/tools")
        async def list_tools():
            """获取可用工具列表"""
            return await self._handle_list_tools()

        @self.app.post("/api/v1/tools/execute")
        async def execute_tool(request: ToolExecuteRequest):
            """执行工具"""
            return await self._handle_execute_tool(request)

        @self.app.get("/api/v1/config")
        async def get_config():
            """获取配置"""
            return await self._handle_get_config()

        @self.app.put("/api/v1/config")
        async def update_config(request: ConfigUpdateRequest):
            """更新配置"""
            return await self._handle_update_config(request)

        @self.app.get("/api/v1/events")
        async def get_recent_events(limit: int = 100):
            """获取最近事件"""
            return await self._handle_get_recent_events(limit)

    async def _handle_websocket(self, websocket: WebSocket, connection_id: str):
        """处理WebSocket连接"""
        await self.connection_manager.connect(websocket, connection_id)

        try:
            # 订阅事件总线
            def event_handler(event: RuntimeEvent):
                asyncio.create_task(
                    self._send_event_to_connection(connection_id, event)
                )

            subscription = subscribe_to_events(event_handler)
            self.connection_manager.connection_subscriptions[connection_id] = subscription

            # 接收消息循环
            while True:
                try:
                    data = await websocket.receive_json()
                    await self._handle_client_message(connection_id, data)
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.error(f"处理WebSocket消息失败: {e}")
                    await self._send_error(connection_id, str(e))

        except Exception as e:
            logger.error(f"WebSocket连接处理失败: {e}")
        finally:
            self.connection_manager.disconnect(connection_id)

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

    async def _handle_client_message(self, connection_id: str, data: Dict[str, Any]):
        """处理客户端消息"""
        try:
            message_type = data.get("type")

            if message_type == "command":
                command = data.get("command")
                payload = data.get("payload", {})
                message_id = data.get("id", str(uuid.uuid4()))

                # 处理命令
                if not isinstance(command, str):
                    raise ValueError("命令必须是字符串")
                response = await self._handle_command(command, payload)

                # 发送响应
                await self.connection_manager.send_message(connection_id, {
                    "type": "response",
                    "id": message_id,
                    "command": command,
                    "payload": response,
                    "timestamp": time.time()
                })

            else:
                logger.warning(f"未知的消息类型: {message_type}")
                await self._send_error(connection_id, f"未知的消息类型: {message_type}")

        except Exception as e:
            logger.error(f"处理客户端消息失败: {e}")
            await self._send_error(connection_id, str(e))

    async def _send_error(self, connection_id: str, error_message: str):
        """发送错误消息"""
        await self.connection_manager.send_message(connection_id, {
            "type": "error",
            "message": error_message,
            "timestamp": time.time()
        })

    async def _handle_command(self, command: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """处理命令"""
        try:
            if command == "send_message":
                content = payload.get("content", "")
                session_id = payload.get("session_id")
                max_turns = payload.get("max_turns")
                thinking_enabled = payload.get("thinking_enabled")
                return await self.api_service.send_message(
                    content, session_id, max_turns, thinking_enabled
                )
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
            else:
                raise ValueError(f"未知命令: {command}")
        except Exception as e:
            logger.error(f"处理命令失败: {command}, 错误: {e}")
            return {"success": False, "error": str(e), "command": command}

    async def _handle_send_message(self, request: MessageRequest) -> Dict[str, Any]:
        """处理发送消息请求（兼容旧版本）"""
        try:
            result = await self.api_service.send_message(
                content=request.content,
                session_id=request.session_id,
                max_turns=request.max_turns,
                thinking_enabled=request.thinking_enabled
            )
            if isinstance(result, dict) and result.get("success") is False:
                raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
            return result
        except ValidationError as e:
            logger.error(f"发送消息校验失败: {e}")
            raise HTTPException(status_code=422, detail=str(e))
        except ValueError as e:
            logger.error(f"发送消息参数错误: {e}")
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def _stream_send_message(self, request: MessageRequest):
        """流式发送消息 - 真正流式版本"""
        import json
        import time

        queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def event_callback(event: RuntimeEvent):
            # 将事件放入队列，注意这是在 asyncio.to_thread 的线程中调用的
            loop.call_soon_threadsafe(queue.put_nowait, event)

        # 在后台启动任务
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
            # 持续从队列读取事件并 yield
            while not send_task.done() or not queue.empty():
                try:
                    # 等待新事件，带超时以便检查 task 状态
                    event = await asyncio.wait_for(queue.get(), timeout=0.2)
                    
                    event_type = event.type
                    if event_type in STREAMABLE_EVENT_TYPES:
                        yield json.dumps({
                            "type": "event",
                            "event_type": event_type,
                            "data": event.data,
                            "timestamp": time.time()
                        }) + "\n"
                except asyncio.TimeoutError:
                    continue

            # 获取最终结果（此时 send_task 已完成）
            result = await send_task

            # 发送完成事件
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

        except Exception as e:
            logger.error(f"流式发送消息失败: {e}")
            yield json.dumps({
                "type": "error",
                "data": {"error": str(e)}
            }) + "\n"
        finally:
            if not send_task.done():
                send_task.cancel()

    async def _handle_list_sessions(self) -> Dict[str, Any]:
        """处理获取会话列表请求"""
        try:
            return await self.api_service.list_sessions()
        except Exception as e:
            logger.error(f"获取会话列表失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def _handle_create_session(self, request: SessionCreateRequest) -> Dict[str, Any]:
        """处理创建会话请求"""
        try:
            return await self.api_service.create_session(
                session_type=request.type,
                title=request.title
            )
        except Exception as e:
            logger.error(f"创建会话失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def _handle_get_session(self, session_id: str) -> Dict[str, Any]:
        """处理获取会话详情请求"""
        try:
            return await self.api_service.get_session(session_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(f"获取会话详情失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def _handle_update_session(self, session_id: str, request: SessionUpdateRequest) -> Dict[str, Any]:
        """处理更新会话请求"""
        try:
            return await self.api_service.update_session(
                session_id=session_id,
                title=request.title
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(f"更新会话失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def _handle_delete_session(self, session_id: str) -> Dict[str, Any]:
        """处理删除会话请求"""
        try:
            return await self.api_service.delete_session(session_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"删除会话失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def _handle_list_tools(self) -> Dict[str, Any]:
        """处理获取工具列表请求"""
        try:
            return await self.api_service.list_tools()
        except Exception as e:
            logger.error(f"获取工具列表失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def _handle_execute_tool(self, request: ToolExecuteRequest) -> Dict[str, Any]:
        """处理执行工具请求"""
        try:
            return await self.api_service.execute_tool(
                name=request.name,
                arguments=request.arguments,
                session_id=request.session_id
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"执行工具失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def _handle_get_config(self) -> Dict[str, Any]:
        """处理获取配置请求"""
        try:
            return await self.api_service.get_config()
        except Exception as e:
            logger.error(f"获取配置失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def _handle_update_config(self, request: ConfigUpdateRequest) -> Dict[str, Any]:
        """处理更新配置请求"""
        try:
            # 将请求转换为字典
            updates = {}
            for field in request.model_fields_set:
                value = getattr(request, field)
                if value is not None:
                    updates[field] = value

            return await self.api_service.update_config(updates)
        except Exception as e:
            logger.error(f"更新配置失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def _handle_get_recent_events(self, limit: int) -> Dict[str, Any]:
        """处理获取最近事件请求"""
        try:
            return await self.api_service.get_recent_events(limit)
        except Exception as e:
            logger.error(f"获取最近事件失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def run(self):
        """运行API服务器"""
        import uvicorn
        uvicorn.run(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info"
        )


# ==================== 工厂函数 ====================

def create_api_server(runtime: AgentRuntime, host: str = "127.0.0.1", port: int = 8000) -> APIServer:
    """创建API服务器实例"""
    return APIServer(runtime, host, port)


def run_api_server(runtime: AgentRuntime, host: str = "127.0.0.1", port: int = 8000):
    """运行API服务器"""
    server = create_api_server(runtime, host, port)
    server.run()


