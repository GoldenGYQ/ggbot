"""Manual end-to-end API tests — requires a running GGbot server."""

#!/usr/bin/env python3
"""测试GGbot API功能"""

import asyncio
import json
import time
import httpx
import websockets
from typing import Dict, Any


class GGbotAPITester:
    """GGbot API测试器"""

    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url
        self.ws_url = base_url.replace("http", "ws") + "/ws"
        self.client = httpx.AsyncClient(timeout=30.0)

    async def test_health(self):
        """测试健康检查"""
        print("测试健康检查...")
        try:
            response = await self.client.get(f"{self.base_url}/api/v1/health")
            print(f"  状态码: {response.status_code}")
            print(f"  响应: {response.json()}")
            return response.status_code == 200
        except Exception as e:
            print(f"  失败: {e}")
            return False

    async def test_get_config(self):
        """测试获取配置"""
        print("测试获取配置...")
        try:
            response = await self.client.get(f"{self.base_url}/api/v1/config")
            print(f"  状态码: {response.status_code}")
            config = response.json()
            print(f"  模型: {config.get('openai_model')}")
            print(f"  工作空间: {config.get('workspace_root')}")
            print(f"  会话ID: {config.get('session_id')}")
            return response.status_code == 200
        except Exception as e:
            print(f"  失败: {e}")
            return False

    async def test_list_sessions(self):
        """测试获取会话列表"""
        print("测试获取会话列表...")
        try:
            response = await self.client.get(f"{self.base_url}/api/v1/sessions")
            print(f"  状态码: {response.status_code}")
            data = response.json()
            print(f"  当前会话: {data.get('current_session_id')}")
            print(f"  会话数量: {len(data.get('sessions', []))}")
            return response.status_code == 200
        except Exception as e:
            print(f"  失败: {e}")
            return False

    async def test_list_tools(self):
        """测试获取工具列表"""
        print("测试获取工具列表...")
        try:
            response = await self.client.get(f"{self.base_url}/api/v1/tools")
            print(f"  状态码: {response.status_code}")
            data = response.json()
            print(f"  工具数量: {data.get('total', 0)}")
            for i, tool in enumerate(data.get('tools', [])[:3]):  # 只显示前3个
                print(f"  工具{i+1}: {tool.get('name')}")
            return response.status_code == 200
        except Exception as e:
            print(f"  失败: {e}")
            return False

    async def test_create_session(self):
        """测试创建会话"""
        print("测试创建会话...")
        try:
            payload = {
                "type": "chat",
                "title": "测试会话"
            }
            response = await self.client.post(
                f"{self.base_url}/api/v1/sessions",
                json=payload
            )
            print(f"  状态码: {response.status_code}")
            data = response.json()
            print(f"  新会话ID: {data.get('id')}")
            print(f"  标题: {data.get('title')}")
            return response.status_code == 200
        except Exception as e:
            print(f"  失败: {e}")
            return False

    async def test_websocket_connection(self):
        """测试WebSocket连接"""
        print("测试WebSocket连接...")
        try:
            async with websockets.connect(self.ws_url) as websocket:
                print("  WebSocket连接成功")

                # 发送测试消息
                test_message = {
                    "type": "command",
                    "id": "test_1",
                    "command": "get_config",
                    "payload": {}
                }
                await websocket.send(json.dumps(test_message))
                print("  发送测试命令")

                # 接收响应
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                data = json.loads(response)
                print(f"  收到响应类型: {data.get('type')}")
                print(f"  命令ID: {data.get('id')}")

                # 等待事件
                print("  等待事件...")
                try:
                    event = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    event_data = json.loads(event)
                    print(f"  收到事件类型: {event_data.get('event_type')}")
                except asyncio.TimeoutError:
                    print("  没有收到事件（正常）")

                return True
        except Exception as e:
            print(f"  失败: {e}")
            return False

    async def test_send_message(self):
        """测试发送消息"""
        print("测试发送消息...")
        try:
            payload = {
                "content": "你好，请介绍一下你自己",
                "max_turns": 2,
                "thinking_enabled": False
            }
            response = await self.client.post(
                f"{self.base_url}/api/v1/messages",
                json=payload
            )
            print(f"  状态码: {response.status_code}")
            data = response.json()
            print(f"  成功: {data.get('success')}")
            print(f"  会话ID: {data.get('session_id')}")
            print(f"  轮次: {data.get('turn_number')}")
            if data.get('success'):
                print(f"  最终响应长度: {len(data.get('final_response', ''))}")
                print(f"  事件数量: {len(data.get('events', []))}")
            return response.status_code == 200 and data.get('success', False)
        except Exception as e:
            print(f"  失败: {e}")
            return False

    async def run_all_tests(self):
        """运行所有测试"""
        print("=" * 60)
        print("开始GGbot API测试")
        print("=" * 60)

        tests = [
            ("健康检查", self.test_health),
            ("获取配置", self.test_get_config),
            ("获取会话列表", self.test_list_sessions),
            ("获取工具列表", self.test_list_tools),
            ("创建会话", self.test_create_session),
            ("WebSocket连接", self.test_websocket_connection),
            ("发送消息", self.test_send_message),
        ]

        results = []
        for name, test_func in tests:
            print(f"\n[{name}]")
            start_time = time.time()
            try:
                success = await test_func()
                elapsed = time.time() - start_time
                status = "✓ 通过" if success else "✗ 失败"
                print(f"  结果: {status} ({elapsed:.2f}s)")
                results.append((name, success, elapsed))
            except Exception as e:
                elapsed = time.time() - start_time
                print(f"  异常: {e}")
                print(f"  结果: ✗ 异常 ({elapsed:.2f}s)")
                results.append((name, False, elapsed))

        # 打印摘要
        print("\n" + "=" * 60)
        print("测试摘要")
        print("=" * 60)

        passed = sum(1 for _, success, _ in results if success)
        total = len(results)
        total_time = sum(elapsed for _, _, elapsed in results)

        print(f"通过: {passed}/{total}")
        print(f"总时间: {total_time:.2f}s")

        for name, success, elapsed in results:
            status = "✓" if success else "✗"
            print(f"  {status} {name}: {elapsed:.2f}s")

        # 清理
        await self.client.aclose()

        return passed == total


async def main():
    """主函数"""
    # 检查API服务器是否运行
    print("检查API服务器状态...")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("http://127.0.0.1:8000/")
            if response.status_code != 200:
                print("错误: API服务器未运行或返回错误")
                print("请先运行: python -m ggbot api")
                return False
    except Exception as e:
        print(f"错误: 无法连接到API服务器: {e}")
        print("请先运行: python -m ggbot api")
        return False

    # 运行测试
    tester = GGbotAPITester()
    all_passed = await tester.run_all_tests()

    if all_passed:
        print("\n🎉 所有测试通过!")
        return True
    else:
        print("\n⚠️  部分测试失败")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
