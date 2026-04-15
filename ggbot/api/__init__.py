"""GGbot API模块 - 提供WebSocket和REST API接口"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = [
    "create_api_server",
    "run_api_server",
    "APIServer",
    "WebSocketManager",
]

from .server import APIServer, create_api_server, run_api_server
from .websocket import WebSocketManager