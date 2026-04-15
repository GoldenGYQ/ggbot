#!/usr/bin/env python3
"""测试流式API"""

import asyncio
import aiohttp
import json
import sys

async def test_streaming_api():
    """测试流式API"""
    url = "http://127.0.0.1:8000/api/v1/messages"

    payload = {
        "content": "你好，请用简短的话介绍一下你自己",
        "stream": True
    }

    print("测试流式API...")
    print(f"请求: {payload['content']}")
    print("-" * 60)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    print(f"错误状态码: {response.status}")
                    print(await response.text())
                    return False

                print(f"状态码: {response.status}")
                print("开始接收流式响应...")
                print("-" * 60)

                event_count = 0
                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                        event_count += 1

                        if data.get("type") == "event":
                            event_type = data.get("event_type")
                            delta = data.get("data", {}).get("delta", "")
                            if delta:
                                print(f"[事件 #{event_count}] {event_type}: {delta}", end="", flush=True)
                            else:
                                print(f"[事件 #{event_count}] {event_type}: {data.get('data')}")
                        elif data.get("type") == "complete":
                            print(f"\n[完成] 会话ID: {data.get('data', {}).get('session_id')}")
                            print(f"      轮次: {data.get('data', {}).get('turn_number')}")
                            print(f"      最终响应长度: {len(data.get('data', {}).get('final_response', ''))}")
                        elif data.get("type") == "error":
                            print(f"[错误] {data.get('data', {}).get('error')}")

                    except json.JSONDecodeError as e:
                        print(f"JSON解析错误: {e}, 行: {line}")

                print("-" * 60)
                print(f"总共收到 {event_count} 个事件")
                return True

    except Exception as e:
        print(f"请求失败: {e}")
        return False

async def test_traditional_api():
    """测试传统API"""
    url = "http://127.0.0.1:8000/api/v1/messages"

    payload = {
        "content": "你好，请用简短的话介绍一下你自己",
        "stream": False
    }

    print("\n测试传统API...")
    print(f"请求: {payload['content']}")
    print("-" * 60)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    print(f"错误状态码: {response.status}")
                    print(await response.text())
                    return False

                data = await response.json()
                print(f"状态码: {response.status}")
                print(f"会话ID: {data.get('session_id')}")
                print(f"轮次: {data.get('turn_number')}")
                print(f"事件数量: {len(data.get('events', []))}")
                print(f"最终响应: {data.get('final_response', '')[:100]}...")
                print("-" * 60)
                return True

    except Exception as e:
        print(f"请求失败: {e}")
        return False

async def main():
    """主函数"""
    print("GGbot流式API测试")
    print("=" * 60)

    # 先测试传统API确保基础功能正常
    print("1. 测试传统API...")
    if not await test_traditional_api():
        print("传统API测试失败，请先启动API服务器")
        print("启动命令: python -m ggbot api")
        return

    # 测试流式API
    print("\n2. 测试流式API...")
    if not await test_streaming_api():
        print("流式API测试失败")
        return

    print("\n所有测试完成！")

if __name__ == "__main__":
    # 检查是否安装了aiohttp
    try:
        import aiohttp
    except ImportError:
        print("请先安装aiohttp: pip install aiohttp")
        sys.exit(1)

    asyncio.run(main())