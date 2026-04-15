# GGbot API 文档

GGbot API 提供了WebSocket和REST API接口，允许外部应用与GGbot智能体进行交互。

## 快速开始

### 1. 安装依赖

```bash
# 确保已安装GGbot
pip install -e .

# 安装API依赖
pip install fastapi uvicorn websockets
```

### 2. 启动API服务器

```bash
# 方法1: 使用CLI命令
python -m ggbot api


# 方法2: 自定义参数
python -m ggbot api --host 0.0.0.0 --port 8080 --workspace-root ./workspace
```

### 3. 验证服务器运行

访问以下地址：
- API文档: http://127.0.0.1:8000/docs
- 健康检查: http://127.0.0.1:8000/api/v1/health
- WebSocket: ws://127.0.0.1:8000/ws

## API端点

### REST API

#### 健康检查
```
GET /api/v1/health
```
返回服务器健康状态。

#### 配置管理
```
GET  /api/v1/config      # 获取配置
PUT  /api/v1/config      # 更新配置
```

#### 会话管理
```
GET    /api/v1/sessions              # 获取会话列表
POST   /api/v1/sessions              # 创建新会话
GET    /api/v1/sessions/{session_id} # 获取会话详情
PUT    /api/v1/sessions/{session_id} # 更新会话
DELETE /api/v1/sessions/{session_id} # 删除会话
```

#### 消息处理
```
POST /api/v1/messages    # 发送消息（支持流式响应）
```

**请求参数：**
```json
{
  "content": "消息内容",
  "session_id": "可选会话ID",
  "max_turns": 8,
  "thinking_enabled": false,
  "stream": false  // 是否启用流式响应
}
```

**流式响应格式（NDJSON）：**
当 `stream=true` 时，API返回Newline Delimited JSON流：
```json
{"type": "event", "event_type": "assistant_delta", "data": {"delta": "Hello"}, "timestamp": 1234567890}
{"type": "event", "event_type": "tool_call", "data": {"name": "search", "arguments": {}}, "timestamp": 1234567891}
{"type": "event", "event_type": "thinking", "data": {"thinking": "I'm thinking..."}, "timestamp": 1234567892}
{"type": "complete", "data": {"session_id": "abc", "final_response": "Hello world!", "success": true}}
{"type": "error", "data": {"error": "错误信息"}}
```

**传统响应格式（JSON）：**
当 `stream=false` 时，API返回完整的JSON响应：
```json
{
  "success": true,
  "session_id": "session_id",
  "turn_number": 1,
  "turns_used": 1,
  "title": "会话标题",
  "events": [...],
  "final_response": "完整响应",
  "has_thinking": false,
  "tool_calls": [...]
}
```

#### 工具管理
```
GET  /api/v1/tools              # 获取工具列表
POST /api/v1/tools/execute      # 执行工具
```

#### 事件管理
```
GET /api/v1/events?limit=100    # 获取最近事件
```

### WebSocket API

WebSocket端点：`ws://127.0.0.1:8000/ws`

#### 消息格式

**发送命令：**
```json
{
  "type": "command",
  "id": "unique_id",
  "command": "command_name",
  "payload": {},
  "timestamp": 1234567890.123
}
```

**接收响应：**
```json
{
  "type": "response",
  "id": "unique_id",
  "command": "command_name",
  "payload": {},
  "timestamp": 1234567890.456
}
```

**接收事件：**
```json
{
  "type": "event",
  "event_type": "assistant_delta",
  "data": {"delta": "Hello"},
  "source": "agent_runtime",
  "timestamp": 1234567890.789,
  "id": "event_id"
}
```

**接收错误：**
```json
{
  "type": "error",
  "message": "错误信息",
  "error_code": "ERROR_CODE",
  "timestamp": 1234567890.123
}
```

#### 支持的命令

1. **send_message** - 发送消息
   ```json
   {
     "command": "send_message",
     "payload": {
       "content": "你好",
       "session_id": "optional_session_id",
       "max_turns": 5,
       "thinking_enabled": false
     }
   }
   ```

2. **list_sessions** - 获取会话列表
   ```json
   {
     "command": "list_sessions",
     "payload": {}
   }
   ```

3. **get_session** - 获取会话详情
   ```json
   {
     "command": "get_session",
     "payload": {
       "session_id": "session_id"
     }
   }
   ```

4. **switch_session** - 切换会话
   ```json
   {
     "command": "switch_session",
     "payload": {
       "session_id": "new_session_id"
     }
   }
   ```

5. **list_tools** - 获取工具列表
   ```json
   {
     "command": "list_tools",
     "payload": {}
   }
   ```

6. **execute_tool** - 执行工具
   ```json
   {
     "command": "execute_tool",
     "payload": {
       "name": "tool_name",
       "arguments": {},
       "session_id": "session_id"
     }
   }
   ```

7. **get_config** - 获取配置
   ```json
   {
     "command": "get_config",
     "payload": {}
   }
   ```

8. **update_config** - 更新配置
   ```json
   {
     "command": "update_config",
     "payload": {
       "updates": {
         "openai_model": "gpt-4.1-mini",
         "max_turns": 10
       }
     }
   }
   ```

9. **get_recent_events** - 获取最近事件
   ```json
   {
     "command": "get_recent_events",
     "payload": {
       "limit": 100
     }
   }
   ```

## 事件类型

GGbot支持以下类型的事件，可通过WebSocket或REST API流式响应获取：

### 流式事件（通过REST API `stream=true` 或 WebSocket）
| 事件类型 | 描述 | 数据格式 | 流式API支持 |
|---------|------|----------|------------|
| `assistant_delta` | 助手流式输出增量 | `{"delta": "text"}` | ✅ |
| `tool_call` | 工具调用 | `{"name": "tool_name", "arguments": {}}` | ✅ |
| `tool_output` | 工具执行输出 | `{"name": "tool_name", "output": "text"}` | ✅ |
| `thinking` | 思考过程 | `{"thinking": "text"}` | ✅ |
| `turn_update` | 轮次更新 | `{"current_turn": 1, "max_turns": 10}` | ✅ |
| `status` | 状态更新 | `{"message": "text", "severity": "info/warning/error"}` | ✅ |

### 控制事件（仅流式API）
| 事件类型 | 描述 | 数据格式 | 说明 |
|---------|------|----------|------|
| `complete` | 处理完成 | `{"session_id": "id", "final_response": "text", "success": true}` | 流式响应结束标志 |
| `error` | 错误事件 | `{"error": "error_message"}` | 流式过程中的错误 |

### 传统事件（通过WebSocket）
| 事件类型 | 描述 | 数据格式 |
|---------|------|----------|
| `assistant_final` | 助手最终输出 | `{"content": "text"}` |
| `tool_result` | 工具执行结果 | `{"name": "tool_name", "result": "output"}` |
| `turn_complete` | 轮次完成 | `{"turns_used": 3}` |
| `session_update` | 会话更新 | `{"session_id": "id", "title": "title"}` |

## 使用示例

### Python客户端示例

```python
import asyncio
import httpx
import aiohttp
import websockets
import json

class GGbotClient:
    def __init__(self, base_url="http://127.0.0.1:8000"):
        self.base_url = base_url
        self.ws_url = base_url.replace("http", "ws") + "/ws"
    
    async def send_message(self, content: str, stream: bool = False, **kwargs):
        """发送消息
        
        Args:
            content: 消息内容
            stream: 是否启用流式响应
            **kwargs: 其他参数（session_id, max_turns, thinking_enabled）
        """
        payload = {"content": content, "stream": stream, **kwargs}
        
        if stream:
            # 流式响应
            return await self._send_message_stream(payload)
        else:
            # 传统响应
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/messages",
                    json=payload
                )
                return response.json()
    
    async def _send_message_stream(self, payload: dict):
        """发送流式消息"""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/v1/messages",
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"API错误: {response.status}, {error_text}")
                
                events = []
                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if not line:
                        continue
                    
                    try:
                        data = json.loads(line)
                        yield data
                        
                        if data.get("type") == "complete":
                            break
                        elif data.get("type") == "error":
                            raise Exception(f"流式错误: {data.get('data', {}).get('error')}")
                            
                    except json.JSONDecodeError as e:
                        print(f"JSON解析错误: {e}, 行: {line}")
    
    async def listen_events(self):
        """监听WebSocket事件"""
        async with websockets.connect(self.ws_url) as websocket:
            while True:
                message = await websocket.recv()
                data = json.loads(message)
                if data.get("type") == "event":
                    print(f"事件: {data.get('event_type')}")
                    print(f"数据: {data.get('data')}")

# 使用示例
async def main():
    client = GGbotClient()
    
    print("1. 传统API调用:")
    response = await client.send_message("你好")
    print(f"响应: {response.get('final_response', '')[:50]}...")
    
    print("\n2. 流式API调用:")
    async for event in client.send_message("今天的天气怎么样？", stream=True):
        if event.get("type") == "event":
            event_type = event.get("event_type")
            delta = event.get("data", {}).get("delta", "")
            if delta:
                print(f"[{event_type}] {delta}", end="", flush=True)
        elif event.get("type") == "complete":
            print(f"\n[完成] 会话ID: {event.get('data', {}).get('session_id')}")
    
    print("\n3. WebSocket监听:")
    # 注意：WebSocket监听是阻塞的，这里只是示例
    # await client.listen_events()

asyncio.run(main())
```

### JavaScript客户端示例

```javascript
// 传统API调用
async function sendMessage(content, stream = false) {
    const response = await fetch('http://127.0.0.1:8000/api/v1/messages', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({content, stream})
    });

    if (!stream) {
        // 传统响应
        const data = await response.json();
        console.log('传统响应:', data);
        return data;
    } else {
        // 流式响应
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const {done, value} = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, {stream: true});
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (!line.trim()) continue;

                try {
                    const data = JSON.parse(line);
                    handleStreamEvent(data);
                } catch (e) {
                    console.error('JSON解析错误:', e, '行:', line);
                }
            }
        }
    }
}

// 处理流式事件
function handleStreamEvent(event) {
    switch (event.type) {
        case 'event':
            const eventType = event.event_type;
            const delta = event.data?.delta || event.data;
            if (delta) {
                // 实时显示增量
                process.stdout.write(`[${eventType}] ${delta}`);
            } else {
                console.log(`[${eventType}]`, event.data);
            }
            break;
        case 'complete':
            console.log('\n[完成] 会话ID:', event.data.session_id);
            console.log('最终响应:', event.data.final_response);
            break;
        case 'error':
            console.error('[错误]', event.data.error);
            break;
    }
}

// WebSocket连接
const ws = new WebSocket('ws://127.0.0.1:8000/ws');

ws.onopen = () => {
    console.log('WebSocket连接已建立');
    
    // 发送命令
    const command = {
        type: 'command',
        id: 'test_' + Date.now(),
        command: 'send_message',
        payload: { content: 'Hello from JavaScript' }
    };
    ws.send(JSON.stringify(command));
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    switch (data.type) {
        case 'event':
            console.log(`事件: ${data.event_type}`, data.data);
            break;
        case 'response':
            console.log(`命令响应: ${data.command}`, data.payload);
            break;
        case 'error':
            console.error(`错误: ${data.message}`);
            break;
    }
};

ws.onerror = (error) => {
    console.error('WebSocket错误:', error);
};

ws.onclose = () => {
    console.log('WebSocket连接已关闭');
};

// 使用示例
async function main() {
    console.log('1. 传统API调用:');
    await sendMessage('你好');
    
    console.log('\n2. 流式API调用:');
    await sendMessage('今天的天气怎么样？', true);
}

// 在浏览器中运行
if (typeof window !== 'undefined') {
    main();
}
```

### cURL示例

```bash
# 健康检查
curl http://127.0.0.1:8000/api/v1/health

# 获取配置
curl http://127.0.0.1:8000/api/v1/config

# 发送消息（传统模式）
curl -X POST http://127.0.0.1:8000/api/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"content": "你好，请介绍一下你自己"}'

# 发送消息（流式模式）
curl -X POST http://127.0.0.1:8000/api/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"content": "你好，请介绍一下你自己", "stream": true}' \
  --no-buffer

# 流式模式实时查看（使用jq处理）
curl -X POST http://127.0.0.1:8000/api/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"content": "今天的天气怎么样？", "stream": true}' \
  --no-buffer | \
  while read -r line; do
    if [ -n "$line" ]; then
      echo "$line" | jq -r '. | select(.type=="event") | "[\(.event_type)] \(.data.delta // .data)"'
    fi
  done

# 获取会话列表
curl http://127.0.0.1:8000/api/v1/sessions

# 获取工具列表
curl http://127.0.0.1:8000/api/v1/tools
```

## 配置说明

### 环境变量

| 变量名 | 描述 | 默认值 |
|--------|------|--------|
| `OPENAI_API_KEY` | OpenAI API密钥 | 无 |
| `OPENAI_MODEL` | 模型名称 | `gpt-4.1-mini` |
| `OPENAI_BASE_URL` | API基础URL | `https://api.openai.com/v1` |
| `GGBOT_WORKSPACE_ROOT` | 工作空间根目录 | 当前目录 |
| `GGBOT_MAX_TURNS` | 最大对话轮次 | `8` |
| `GGBOT_THINKING_ENABLED` | 启用思考功能 | `false` |
| `GGBOT_STREAM_ENABLED` | 启用流式响应 | `true` |
| `GGBOT_STREAM_DELAY_MS` | 流式事件延迟（毫秒） | `50` |

**流式相关配置说明：**
- `GGBOT_STREAM_ENABLED`: 控制是否启用流式响应功能
- `GGBOT_STREAM_DELAY_MS`: 控制流式事件发送的延迟，用于控制实时性体验

### 配置文件

GGbot会从以下位置加载配置（按优先级）：
1. 命令行参数
2. 环境变量
3. `.env`文件
4. `.ggbot/config.toml`
5. 默认值

## 开发指南

### 项目结构

```
ggbot/api/
├── __init__.py          # 模块导出
├── server.py           # FastAPI服务器
├── websocket.py        # WebSocket管理器
└── services.py         # 业务逻辑服务
```

### 添加新的API端点

1. 在 `server.py` 中添加路由定义
2. 在 `services.py` 中实现业务逻辑
3. 在数据模型中定义请求/响应格式
4. 更新文档

### 测试API

```bash
# 运行单元测试
python -m pytest tests/test_api.py -v

# 运行集成测试
python test_api.py

# 运行示例
python examples/api_example.py
```

## 故障排除

### 常见问题

1. **API服务器无法启动**
   - 检查端口是否被占用：`netstat -an | grep 8000`
   - 检查依赖是否安装：`pip list | grep fastapi`
   - 检查Python版本：`python --version`

2. **WebSocket连接失败**
   - 检查服务器是否运行：`curl http://127.0.0.1:8000/health`
   - 检查防火墙设置
   - 使用 `wscat` 测试连接：`wscat -c ws://127.0.0.1:8000/ws`

3. **API调用返回错误**
   - 检查请求格式是否正确
   - 查看服务器日志：启动时添加 `--log-level debug`
   - 检查环境变量设置

4. **消息发送无响应**
   - 检查 `OPENAI_API_KEY` 是否正确设置
   - 检查网络连接
   - 查看模型是否可用

5. **流式API不工作**
   - 检查 `stream` 参数是否正确设置为 `true`
   - 检查客户端是否支持流式响应（现代浏览器或支持Streams API的HTTP客户端）
   - 使用 `--no-buffer` 参数运行curl命令
   - 检查服务器日志查看流式处理是否有错误

6. **流式响应中断**
   - 检查网络连接稳定性
   - 增加客户端超时时间
   - 检查服务器负载是否过高
   - 验证NDJSON格式是否正确（每行一个完整的JSON对象）

### 日志查看

```bash
# 启用详细日志
python -m ggbot api --log-level debug

# 查看实时日志
tail -f .ggbot/logs/api.log
```

## 性能优化

### 建议配置

1. **WebSocket连接池**：限制最大连接数
2. **事件缓冲区**：限制事件历史大小
3. **消息压缩**：对大型响应启用压缩
4. **连接超时**：设置合理的超时时间

### 监控指标

- 活动连接数
- 消息处理延迟
- 内存使用情况
- 错误率

## 安全考虑

1. **生产环境部署**
   - 使用HTTPS/WSS
   - 设置API密钥认证
   - 启用CORS限制
   - 配置防火墙规则

2. **输入验证**
   - 验证所有输入参数
   - 限制消息长度
   - 过滤恶意内容

3. **访问控制**
   - 实现用户认证
   - 会话隔离
   - 权限管理

## 更新日志

### v0.2.0 (2024-04-16)
- **新增流式API支持**：`/api/v1/messages` 端点支持 `stream=true` 参数
- **增量流式更新**：实时显示助手思考过程和工具调用
- **NDJSON响应格式**：支持Newline Delimited JSON流式响应
- **前端流式处理**：示例前端支持实时显示增量输出
- **双模式兼容**：传统JSON响应和流式响应并存

### v0.1.0 (2024-04-15)
- 初始版本发布
- 支持REST API和WebSocket
- 完整的会话管理
- 实时事件推送
- 工具执行接口

## 贡献指南

欢迎提交Issue和Pull Request！

1. Fork项目
2. 创建功能分支
3. 提交更改
4. 推送分支
5. 创建Pull Request

## 许可证

MIT License