import json
import asyncio
import httpx

async def test_plan_streaming():
    url = "http://127.0.0.1:8000/api/v1/messages"
    payload = {
        "content": "请先搜索 2026 年 AI 趋势，然后提炼 3 个结论。请务必使用 <plan> 标签列出你的步骤。",
        "stream": True,
        "thinking_enabled": True
    }
    
    print(f"发送请求到 {url}...")
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("POST", url, json=payload) as response:
            if response.status_code != 200:
                print(f"错误: {response.status_code}")
                return

            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                
                try:
                    event = json.loads(line)
                    if event.get("type") == "event":
                        event_type = event.get("event_type")
                        if event_type == "plan_update":
                            print("\n[PLAN UPDATE DETECTED!]")
                            print(json.dumps(event.get("data"), indent=2, ensure_ascii=False))
                        elif event_type == "assistant_delta":
                            # print(event["data"]["delta"], end="", flush=True)
                            pass
                    elif event.get("type") == "complete":
                        print("\n[STREAM COMPLETE]")
                except Exception as e:
                    print(f"\n解析错误: {e}")

if __name__ == "__main__":
    asyncio.run(test_plan_streaming())
