#!/usr/bin/env python3
"""GGbot API使用示例"""

import asyncio
import json
import time
import httpx
import websockets
from typing import Dict, Any, List, Optional


class GGbotAPIClient:
    """GGbot API客户端"""

    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url
        self.ws_url = base_url.replace("http", "ws") + "/ws"
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """关闭客户端"""
        await self.client.aclose()

    # ==================== REST API方法 ====================

    async def get_health(self) -> Dict[str, Any]:
        """获取健康状态"""
        response = await self.client.get(f"{self.base_url}/api/v1/health")
        response.raise_for_status()
        return response.json()

    async def get_config(self) -> Dict[str, Any]:
        """获取配置"""
        response = await self.client.get(f"{self.base_url}/api/v1/config")
        response.raise_for_status()
        return response.json()

    async def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """更新配置"""
        response = await self.client.put(
            f"{self.base_url}/api/v1/config",
            json=updates
        )
        response.raise_for_status()
        return response.json()

    async def list_sessions(self) -> Dict[str, Any]:
        """获取会话列表"""
        response = await self.client.get(f"{self.base_url}/api/v1/sessions")
        response.raise_for_status()
        return response.json()

    async def create_session(self, session_type: str = "chat", title: Optional[str] = None) -> Dict[str, Any]:
        """创建会话"""
        payload = {"type": session_type}
        if title:
            payload["title"] = title

        response = await self.client.post(
            f"{self.base_url}/api/v1/sessions",
            json=payload
        )
        response.raise_for_status()
        return response.json()

    async def get_session(self, session_id: str) -> Dict[str, Any]:
        """获取会话详情"""
        response = await self.client.get(f"{self.base_url}/api/v1/sessions/{session_id}")
        response.raise_for_status()
        return response.json()

    async def send_message(self, content: str, session_id: Optional[str] = None,
                          max_turns: Optional[int] = None,
                          thinking_enabled: Optional[bool] = None) -> Dict[str, Any]:
        """发送消息"""
        payload = {"content": content}
        if session_id:
            payload["session_id"] = session_id
        if max_turns is not None:
            payload["max_turns"] = max_turns
        if thinking_enabled is not None:
            payload["thinking_enabled"] = thinking_enabled

        response = await self.client.post(
            f"{self.base_url}/api/v1/messages",
            json=payload
        )
        response.raise_for_status()
        return response.json()

    async def list_tools(self) -> Dict[str, Any]:
        """获取工具列表"""
        response = await self.client.get(f"{self.base_url}/api/v1/tools")
        response.raise_for_status()
        return response.json()

    async def execute_tool(self, name: str, arguments: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        """执行工具"""
        payload = {
            "name": name,
            "arguments": arguments,
            "session_id": session_id
        }
        response = await self.client.post(
            f"{self.base_url}/api/v1/tools/execute",
            json=payload
        )
        response.raise_for_status()
        return response.json()

    async def get_recent_events(self, limit: int = 100) -> Dict[str, Any]:
        """获取最近事件"""
        response = await self.client.get(
            f"{self.base_url}/api/v1/events",
            params={"limit": limit}
        )
        response.raise_for_status()
        return response.json()

    # ==================== WebSocket方法 ====================

    async def connect_websocket(self) -> websockets.WebSocketClientProtocol:
        """连接WebSocket"""
        return await websockets.connect(self.ws_url)

    async def send_websocket_command(self, websocket: websockets.WebSocketClientProtocol,
                                    command: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """发送WebSocket命令"""
        message_id = f"cmd_{int(time.time() * 1000)}"
        message = {
            "type": "command",
            "id": message_id,
            "command": command,
            "payload": payload,
            "timestamp": time.time()
        }

        await websocket.send(json.dumps(message))

        # 等待响应
        while True:
            response = await websocket.recv()
            data = json.loads(response)

            if data.get("type") == "response" and data.get("id") == message_id:
                return data.get("payload", {})

            elif data.get("type") == "error" and data.get("id") == message_id:
                raise Exception(f"命令执行错误: {data.get('message')}")

    async def listen_events(self, websocket: websockets.WebSocketClientProtocol,
                           callback: callable, timeout: float = 10.0):
        """监听事件"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                data = json.loads(response)

                if data.get("type") == "event":
                    await callback(data)
                elif data.get("type") == "error":
                    print(f"收到错误: {data.get('message')}")

            except asyncio.TimeoutError:
                continue


# ==================== 使用示例 ====================

async def example_basic_usage():
    """基础使用示例"""
    print("=" * 60)
    print("GGbot API基础使用示例")
    print("=" * 60)

    client = GGbotAPIClient()

    try:
        # 1. 检查API状态
        print("\n1. 检查API状态")
        health = await client.get_health()
        print(f"   状态: {health.get('status')}")
        print(f"   版本: {health.get('version', '未知')}")

        # 2. 获取配置
        print("\n2. 获取配置")
        config = await client.get_config()
        print(f"   模型: {config.get('openai_model')}")
        print(f"   工作空间: {config.get('workspace_root')}")
        print(f"   当前会话: {config.get('session_id')}")

        # 3. 获取会话列表
        print("\n3. 获取会话列表")
        sessions = await client.list_sessions()
        print(f"   当前会话ID: {sessions.get('current_session_id')}")
        print(f"   会话数量: {len(sessions.get('sessions', []))}")

        # 4. 创建新会话
        print("\n4. 创建新会话")
        new_session = await client.create_session(
            session_type="chat",
            title="API测试会话"
        )
        print(f"   新会话ID: {new_session.get('id')}")
        print(f"   标题: {new_session.get('title')}")

        # 5. 发送消息
        print("\n5. 发送消息")
        response = await client.send_message(
            content="你好，请用简短的话介绍一下你自己",
            max_turns=2,
            thinking_enabled=False
        )

        if response.get("success"):
            print(f"   成功: 是")
            print(f"   会话ID: {response.get('session_id')}")
            print(f"   轮次: {response.get('turn_number')}")
            final_response = response.get("final_response", "")
            print(f"   响应预览: {final_response[:100]}...")
            print(f"   事件数量: {len(response.get('events', []))}")
        else:
            print(f"   失败: {response.get('error')}")

        # 6. 获取工具列表
        print("\n6. 获取工具列表")
        tools = await client.list_tools()
        print(f"   工具总数: {tools.get('total')}")
        for i, tool in enumerate(tools.get('tools', [])[:5]):  # 显示前5个
            print(f"   {i+1}. {tool.get('name')}: {tool.get('description', '')[:50]}...")

        # 7. 获取最近事件
        print("\n7. 获取最近事件")
        events = await client.get_recent_events(limit=5)
        print(f"   事件总数: {events.get('total')}")
        print(f"   最近事件: {len(events.get('events', []))}")

    except Exception as e:
        print(f"错误: {e}")
    finally:
        await client.close()


async def example_websocket_usage():
    """WebSocket使用示例"""
    print("\n" + "=" * 60)
    print("WebSocket使用示例")
    print("=" * 60)

    client = GGbotAPIClient()

    try:
        # 连接WebSocket
        print("\n1. 连接WebSocket...")
        websocket = await client.connect_websocket()
        print("   WebSocket连接成功")

        # 定义事件回调函数
        async def handle_event(event_data: Dict[str, Any]):
            event_type = event_data.get("event_type")
            timestamp = event_data.get("timestamp")
            print(f"   收到事件: {event_type} ({time.strftime('%H:%M:%S', time.localtime(timestamp))})")

        # 监听事件（异步）
        listener_task = asyncio.create_task(
            client.listen_events(websocket, handle_event, timeout=5.0)
        )

        # 发送命令
        print("\n2. 发送WebSocket命令...")

        # 获取配置
        print("   a) 获取配置")
        config_result = await client.send_websocket_command(
            websocket, "get_config", {}
        )
        print(f"     模型: {config_result.get('openai_model')}")

        # 获取会话列表
        print("   b) 获取会话列表")
        sessions_result = await client.send_websocket_command(
            websocket, "list_sessions", {}
        )
        print(f"     会话数量: {len(sessions_result.get('sessions', []))}")

        # 发送消息
        print("   c) 发送消息")
        message_result = await client.send_websocket_command(
            websocket, "send_message", {
                "content": "今天的天气怎么样？",
                "max_turns": 1
            }
        )
        if message_result.get("success"):
            print(f"     消息发送成功")
            print(f"     响应长度: {len(message_result.get('final_response', ''))}")
        else:
            print(f"     消息发送失败: {message_result.get('error')}")

        # 等待事件监听完成
        print("\n3. 等待事件...")
        try:
            await asyncio.wait_for(listener_task, timeout=6.0)
        except asyncio.TimeoutError:
            print("   事件监听超时")

        # 关闭WebSocket
        await websocket.close()
        print("\n   WebSocket连接已关闭")

    except Exception as e:
        print(f"错误: {e}")
    finally:
        await client.close()


async def example_advanced_usage():
    """高级使用示例"""
    print("\n" + "=" * 60)
    print("高级使用示例")
    print("=" * 60)

    client = GGbotAPIClient()

    try:
        # 1. 创建多个会话
        print("\n1. 创建多个会话")
        sessions = []
        for i in range(3):
            session = await client.create_session(
                session_type="chat",
                title=f"测试会话 {i+1}"
            )
            sessions.append(session)
            print(f"   创建会话 {i+1}: {session.get('id')}")

        # 2. 在不同会话中发送消息
        print("\n2. 在不同会话中发送消息")
        for i, session in enumerate(sessions):
            print(f"   在会话 {i+1} 中发送消息...")
            response = await client.send_message(
                content=f"这是会话 {i+1} 的测试消息",
                session_id=session.get("id"),
                max_turns=1
            )
            if response.get("success"):
                print(f"     成功: {response.get('session_id')}")
            else:
                print(f"     失败: {response.get('error')}")

        # 3. 获取所有会话详情
        print("\n3. 获取所有会话详情")
        all_sessions = await client.list_sessions()
        for session_info in all_sessions.get("sessions", []):
            print(f"   会话: {session_info.get('title')}")
            print(f"     ID: {session_info.get('id')}")
            print(f"     消息数: {session_info.get('message_count')}")
            print(f"     用户轮次: {session_info.get('user_turns')}")

        # 4. 执行工具
        print("\n4. 执行工具")
        tools = await client.list_tools()
        if tools.get("tools"):
            # 尝试执行第一个工具（如果有合适的参数）
            first_tool = tools.get("tools")[0]
            tool_name = first_tool.get("name")

            # 根据工具类型选择参数
            if "file" in tool_name.lower():
                # 文件工具
                arguments = {"path": "."}
            elif "shell" in tool_name.lower():
                # Shell工具
                arguments = {"command": "echo 'Hello from API'"}
            else:
                # 其他工具使用空参数
                arguments = {}

            print(f"   执行工具: {tool_name}")
            try:
                result = await client.execute_tool(
                    name=tool_name,
                    arguments=arguments,
                    session_id=all_sessions.get("current_session_id")
                )
                if result.get("success"):
                    print(f"     成功: {result.get('result')[:100]}...")
                else:
                    print(f"     失败: {result.get('error')}")
            except Exception as e:
                print(f"     执行失败: {e}")

    except Exception as e:
        print(f"错误: {e}")
    finally:
        await client.close()


async def main():
    """主函数"""
    print("GGbot API使用示例")
    print("=" * 60)
    print("注意：请先启动API服务器：python -m ggbot api")
    print("=" * 60)

    # 检查API服务器是否运行
    try:
        client = GGbotAPIClient()
        await client.get_health()
        await client.close()
    except Exception as e:
        print(f"错误: 无法连接到API服务器: {e}")
        print("请先运行: python -m ggbot api")
        return

    # 运行示例
    await example_basic_usage()
    await example_websocket_usage()
    await example_advanced_usage()

    print("\n" + "=" * 60)
    print("示例完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())