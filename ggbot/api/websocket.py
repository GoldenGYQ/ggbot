"""WebSocket管理器 - 处理实时事件推送"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Set, Callable

from fastapi import WebSocket

from ..core.domain import RuntimeEvent
from ..core.event_bus import get_global_event_bus, subscribe_to_events

logger = logging.getLogger(__name__)


class WebSocketManager:
    """WebSocket管理器 - 处理连接和事件推送"""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_info: Dict[str, Dict[str, Any]] = {}
        self.event_handlers: Dict[str, List[Callable]] = {}
        self._subscription = None

    async def connect(self, websocket: WebSocket) -> str:
        """建立WebSocket连接"""
        await websocket.accept()
        connection_id = str(uuid.uuid4())

        self.active_connections[connection_id] = websocket
        self.connection_info[connection_id] = {
            "connected_at": time.time(),
            "last_activity": time.time(),
            "subscriptions": set(),  # 订阅的事件类型
            "metadata": {}
        }

        logger.info(f"WebSocket连接已建立: {connection_id}")

        # 如果是第一个连接，开始监听事件
        if len(self.active_connections) == 1:
            self._start_event_listening()

        return connection_id

    def disconnect(self, connection_id: str):
        """断开WebSocket连接"""
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]

        if connection_id in self.connection_info:
            del self.connection_info[connection_id]

        logger.info(f"WebSocket连接已断开: {connection_id}")

        # 如果没有活动连接，停止监听事件
        if not self.active_connections and self._subscription:
            get_global_event_bus().unsubscribe(self._subscription)
            self._subscription = None

    def update_activity(self, connection_id: str):
        """更新连接活动时间"""
        if connection_id in self.connection_info:
            self.connection_info[connection_id]["last_activity"] = time.time()

    def subscribe_to_event_type(self, connection_id: str, event_type: str):
        """订阅特定类型的事件"""
        if connection_id in self.connection_info:
            self.connection_info[connection_id]["subscriptions"].add(event_type)

    def unsubscribe_from_event_type(self, connection_id: str, event_type: str):
        """取消订阅特定类型的事件"""
        if connection_id in self.connection_info:
            self.connection_info[connection_id]["subscriptions"].discard(event_type)

    def set_metadata(self, connection_id: str, key: str, value: Any):
        """设置连接元数据"""
        if connection_id in self.connection_info:
            self.connection_info[connection_id]["metadata"][key] = value

    def get_metadata(self, connection_id: str, key: str, default: Any = None) -> Any:
        """获取连接元数据"""
        if connection_id in self.connection_info:
            return self.connection_info[connection_id]["metadata"].get(key, default)
        return default

    def _start_event_listening(self):
        """开始监听事件总线"""
        def event_handler(event: RuntimeEvent):
            asyncio.create_task(self._broadcast_event(event))

        self._subscription = subscribe_to_events(event_handler)
        logger.info("开始监听事件总线")

    async def _broadcast_event(self, event: RuntimeEvent):
        """广播事件到所有连接"""
        event_message = self._format_event_message(event)

        # 发送到所有连接
        disconnected = []
        for connection_id, websocket in self.active_connections.items():
            try:
                # 检查连接是否订阅了此事件类型
                subscriptions = self.connection_info[connection_id]["subscriptions"]
                if not subscriptions or event.type in subscriptions:
                    await websocket.send_json(event_message)
            except Exception as e:
                logger.error(f"发送事件到连接 {connection_id} 失败: {e}")
                disconnected.append(connection_id)

        # 清理断开连接
        for connection_id in disconnected:
            self.disconnect(connection_id)

    def _format_event_message(self, event: RuntimeEvent) -> Dict[str, Any]:
        """格式化事件消息"""
        return {
            "type": "event",
            "event_type": event.type,
            "data": event.data,
            "source": event.source,
            "timestamp": time.time(),
            "id": str(uuid.uuid4())
        }

    async def send_message(self, connection_id: str, message: Dict[str, Any]):
        """发送消息到指定连接"""
        if connection_id in self.active_connections:
            try:
                await self.active_connections[connection_id].send_json(message)
                self.update_activity(connection_id)
            except Exception as e:
                logger.error(f"发送消息到连接 {connection_id} 失败: {e}")
                self.disconnect(connection_id)

    async def broadcast(self, message: Dict[str, Any], event_type: Optional[str] = None):
        """广播消息到所有连接"""
        disconnected = []
        for connection_id, websocket in self.active_connections.items():
            try:
                # 如果指定了事件类型，只发送给订阅了该类型的连接
                if event_type:
                    subscriptions = self.connection_info[connection_id]["subscriptions"]
                    if event_type not in subscriptions:
                        continue

                await websocket.send_json(message)
                self.update_activity(connection_id)
            except Exception as e:
                logger.error(f"广播消息到连接 {connection_id} 失败: {e}")
                disconnected.append(connection_id)

        # 清理断开连接
        for connection_id in disconnected:
            self.disconnect(connection_id)

    async def send_command_response(self, connection_id: str, command_id: str, result: Any, error: bool = False):
        """发送命令响应"""
        message = {
            "type": "command_response",
            "command_id": command_id,
            "result": result,
            "error": error,
            "timestamp": time.time()
        }
        await self.send_message(connection_id, message)

    async def send_error(self, connection_id: str, error_message: str, error_code: Optional[str] = None):
        """发送错误消息"""
        message = {
            "type": "error",
            "message": error_message,
            "error_code": error_code,
            "timestamp": time.time()
        }
        await self.send_message(connection_id, message)

    def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接统计信息"""
        total_connections = len(self.active_connections)
        now = time.time()

        # 计算活动连接（最近5分钟内有活动）
        active_connections = 0
        for info in self.connection_info.values():
            if now - info["last_activity"] < 300:  # 5分钟
                active_connections += 1

        # 统计订阅情况
        subscription_stats = {}
        for info in self.connection_info.values():
            for event_type in info["subscriptions"]:
                subscription_stats[event_type] = subscription_stats.get(event_type, 0) + 1

        return {
            "total_connections": total_connections,
            "active_connections": active_connections,
            "subscription_stats": subscription_stats,
            "connection_ids": list(self.active_connections.keys())
        }

    def cleanup_inactive_connections(self, timeout_seconds: int = 300):
        """清理不活动的连接"""
        now = time.time()
        inactive = []

        for connection_id, info in self.connection_info.items():
            if now - info["last_activity"] > timeout_seconds:
                inactive.append(connection_id)

        for connection_id in inactive:
            logger.info(f"清理不活动连接: {connection_id}")
            self.disconnect(connection_id)

        return len(inactive)


# 全局WebSocket管理器实例
_global_websocket_manager: Optional[WebSocketManager] = None


def get_global_websocket_manager() -> WebSocketManager:
    """获取全局WebSocket管理器"""
    global _global_websocket_manager
    if _global_websocket_manager is None:
        _global_websocket_manager = WebSocketManager()
    return _global_websocket_manager


def create_websocket_manager() -> WebSocketManager:
    """创建新的WebSocket管理器"""
    return WebSocketManager()