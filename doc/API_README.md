# GGbot API 业务开发手册

这份文档的目标是：你只看这一份，就能把 GGbot 接进完整业务流程（实时对话、工具调用、审批、会话管理、日志审计）。

适用读者：

- 业务后端：把 GGbot 接进现有系统
- 前端工程师：做 WebSocket 实时聊天/协同界面
- 平台维护者：做运维页、审计页、配置管理页

## 1. 先建立正确心智模型

- 对话主链路是 **WebSocket `/ws` + `send_message`**。
- REST 主要用于 **管理能力**：会话、工具、配置、事件查询。
- Client 会收到两类返回：
- `type=event`：过程流（增量、工具、状态、审批请求）
- `type=response`：本次命令结束结果（命令执行结果）

一句话：**WS 做实时业务，REST 做管理和辅助。**

## 2. 本地启动与连通性检查

在仓库根目录执行：

```bash
uv venv .venv
uv sync --extra dev
uv run ggbot api --host 127.0.0.1 --port 8000
```

启动后检查：

- OpenAPI：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/api/v1/health`
- WebSocket：`ws://127.0.0.1:8000/ws`

健康检查示例：

```bash
curl http://127.0.0.1:8000/api/v1/health
```

## 3. API 全景图（怎么选）

### 3.1 WebSocket（实时业务入口）

连接：`ws://127.0.0.1:8000/ws`

命令：

- `send_message`
- `stop_message`
- `list_sessions`
- `get_session`
- `switch_session`
- `list_tools`
- `execute_tool`
- `get_config`
- `update_config`
- `get_recent_events`
- `permission_response`

### 3.2 REST（管理接口）

- `GET /api/v1/health`
- `GET /api/v1/sessions`
- `POST /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}`
- `GET /api/v1/sessions/{session_id}/model-io`
- `PUT /api/v1/sessions/{session_id}`
- `DELETE /api/v1/sessions/{session_id}`
- `GET /api/v1/tools`
- `POST /api/v1/tools/execute`
- `GET /api/v1/config`
- `PUT /api/v1/config`
- `GET /api/v1/events?limit=100`

说明：

- `POST /api/v1/messages` 已关闭（deprecated），请改用 WS `send_message`。
- 权限审批的 HTTP 接口也已关闭，请用 WS `permission_response`。

## 4. WebSocket 协议与字段

### 4.1 命令消息（客户端 -> 服务端）

```json
{
  "type": "command",
  "id": "cmd_001",
  "command": "send_message",
  "payload": {
    "content": "请给我一个发布 checklist",
    "session_id": "api",
    "max_turns": 4,
    "thinking_enabled": false
  }
}
```

### 4.2 命令结果（服务端 -> 客户端）

```json
{
  "type": "response",
  "id": "cmd_001",
  "command": "send_message",
  "payload": {
    "success": true,
    "session_id": "api",
    "turn_number": 2,
    "turns_used": 1,
    "final_response": "这里是最终回复..."
  },
  "timestamp": 1730000000.123
}
```

### 4.3 过程事件（服务端 -> 客户端）

```json
{
  "type": "event",
  "event_type": "assistant_delta",
  "data": {
    "delta": "你好"
  },
  "source": "agent_runtime",
  "timestamp": 1730000000.123
}
```

### 4.4 错误消息（服务端 -> 客户端）

```json
{
  "type": "error",
  "message": "缺少session_id参数",
  "timestamp": 1730000000.123
}
```

## 5. WebSocket 命令清单（带小 case）

### 5.1 `send_message`（核心）

用途：发起一次 agent 执行，可收到增量文本、工具事件、最终结果。

payload 字段：

- `content`：用户输入（必填）
- `session_id`：会话 ID（选填，不传则使用当前会话）
- `max_turns`：限制本次最大轮次（选填）
- `thinking_enabled`：是否启用 thinking（选填，必须是布尔值）
- `provider_thinking`：是否让 provider 走思考模型（选填，必须是布尔值；在旧 DeepSeek 模式下会在 `deepseek-chat`/`deepseek-reasoner` 间按本次请求切换）

Vue 前端开关示例（同一个命令，只改布尔值）：

```json
{
  "type": "command",
  "id": "msg_on",
  "command": "send_message",
  "payload": {
    "content": "请分析这个方案",
    "session_id": "api",
    "thinking_enabled": true
  }
}
```

```json
{
  "type": "command",
  "id": "msg_off",
  "command": "send_message",
  "payload": {
    "content": "直接给结论",
    "session_id": "api",
    "thinking_enabled": false
  }
}
```

小 case：聊天输入框发送

- 前端点击发送后发 `send_message`
- 收到 `assistant_delta` 就拼接 UI 文本
- 收到 `tool_call/tool_result` 就显示“执行中/执行结果”
- 收到 `response` 结束 loading

### 5.2 `stop_message`

用途：中断某会话当前生成任务。

payload：

```json
{"session_id": "api"}
```

返回关键字段：

- `success`
- `stopped`
- `message`

小 case：用户点击“停止生成”

- 立刻发 `stop_message`
- 若 `stopped=true`，将输入框恢复可编辑

### 5.3 会话相关命令

命令：

- `list_sessions`
- `get_session`
- `switch_session`

`get_session` / `switch_session` payload：

```json
{"session_id": "xxxx"}
```

小 case：左侧会话栏

- 首屏发 `list_sessions` 渲染会话列表
- 点击会话发 `switch_session`
- 再发 `get_session` 拉完整消息用于回显

### 5.4 工具相关命令

命令：

- `list_tools`
- `execute_tool`

`execute_tool` payload：

```json
{
  "name": "web_fetch",
  "arguments": {"url": "https://example.com"},
  "session_id": "api"
}
```

小 case：后台“工具调试页”

- 发 `list_tools` 生成动态表单
- 用户填参数后发 `execute_tool`
- 展示 `result` 或 `error`

### 5.5 配置命令

命令：

- `get_config`
- `update_config`

`update_config` payload：

```json
{
  "updates": {
    "max_turns": 6,
    "thinking_enabled": false
  }
}
```

小 case：管理后台配置页

- 初始化发 `get_config`
- 修改后发 `update_config`
- 成功后用返回值覆盖本地配置状态

### 5.6 `permission_response`（审批流）

用途：响应服务端发出的 `permission_request`。

payload：

```json
{
  "request_id": "perm_xxx",
  "allowed": true,
  "reason": "管理员批准",
  "session_id": "api"
}
```

小 case：高风险工具审批

- 收到 `permission_request` 后弹确认框
- 用户确认后回 `permission_response`
- 再等待后续 `tool_result` / `response`

## 6. 关键事件（前端渲染建议）

- `assistant_delta`：逐字渲染正文
- `assistant_final`：收口文本，可用于兜底覆盖
- `tool_call`：展示“调用了什么工具 + 参数”
- `tool_result`：展示工具输出（可折叠）
- `thinking`：调试态展示，不建议默认暴露给普通用户
- `turn_update`：显示阶段状态
- `turn_complete`：一轮结束标记
- `status`：提示信息
- `permission_request`：进入审批流程
- `permission_response`：审批结果事件

前端最低建议：

- 事件按时间顺序 append
- 对 `assistant_delta` 做 session 级缓冲
- `response/error` 到达后结束当前命令状态

## 7. REST 接口详解（带可复制示例）

以下示例都假设：

```bash
BASE=http://127.0.0.1:8000
```

### 7.1 会话管理

列出会话：

```bash
curl "$BASE/api/v1/sessions"
```

创建会话：

```bash
curl -X POST "$BASE/api/v1/sessions" \
  -H "Content-Type: application/json" \
  -d '{"type":"chat","title":"发布机器人"}'
```

获取会话详情：

```bash
curl "$BASE/api/v1/sessions/<session_id>"
```

获取模型原始输入输出：

```bash
curl "$BASE/api/v1/sessions/<session_id>/model-io"
```

更新会话标题：

```bash
curl -X PUT "$BASE/api/v1/sessions/<session_id>" \
  -H "Content-Type: application/json" \
  -d '{"title":"新的会话标题"}'
```

删除会话：

```bash
curl -X DELETE "$BASE/api/v1/sessions/<session_id>"
```

### 7.2 工具管理

查看工具列表：

```bash
curl "$BASE/api/v1/tools"
```

执行工具：

```bash
curl -X POST "$BASE/api/v1/tools/execute" \
  -H "Content-Type: application/json" \
  -d '{"name":"web_fetch","arguments":{"url":"https://example.com"},"session_id":"api"}'
```

### 7.3 配置管理

查询配置：

```bash
curl "$BASE/api/v1/config"
```

更新配置：

```bash
curl -X PUT "$BASE/api/v1/config" \
  -H "Content-Type: application/json" \
  -d '{"max_turns":6,"thinking_enabled":false}'
```

### 7.4 事件查询

查询最近事件：

```bash
curl "$BASE/api/v1/events?limit=100"
```

典型用途：

- 运营后台查看近实时事件
- 问题排查时做快速回看

## 8. 业务落地小 case（端到端）

### 8.1 Case A：实时聊天助手（最常见）

目标：做一个“类似 ChatGPT”的网页聊天。

实现步骤：

- 页面加载时建立 WS 连接
- 发送 `send_message`
- 用 `assistant_delta` 渲染增量
- 用 `tool_call/tool_result` 渲染过程卡片
- 用 `response` 结束回合并解锁输入框

扩展点：

- 加上 `stop_message` 支持“停止生成”
- 会话侧栏结合 `list_sessions/switch_session`

### 8.2 Case B：审批型 Copilot（企业内网常见）

目标：高风险工具（例如 shell）必须人工审批。

实现步骤：

- 正常发 `send_message`
- 收到 `permission_request` 时暂停“自动继续”
- UI 弹窗显示风险信息（工具名、参数、原因）
- 用户决策后发 `permission_response`
- 继续接收后续工具/文本事件

关键收益：

- 业务上可解释、可追责
- 不需要改 AgentLoop 代码即可接入审批

### 8.3 Case C：运营观测后台

目标：做一个“会话 + 事件 + 配置”的管理页面。

实现步骤：

- 会话页：用 `/api/v1/sessions` + `/api/v1/sessions/{id}`
- 事件页：用 `/api/v1/events?limit=...`
- 配置页：用 `/api/v1/config` + `/api/v1/config (PUT)`

提示：

- 事件页用于“快速观察”
- 审计与回放建议配合 transcript JSONL

## 9. 前端状态机建议（避免错乱）

每条命令维护一个 `command_id` 状态：

- `pending`：已发送命令，等待事件/响应
- `streaming`：收到 `event`
- `done`：收到 `response`
- `error`：收到 `error` 或连接断开

必做策略：

- 同时支持多命令并发时，按 `id` 归并 UI 状态
- 断线重连后先拉 `get_session` 再继续发送新命令

## 10. Python/JavaScript 最小可运行示例

### 10.1 Python（WebSocket）

```python
import asyncio
import json
import websockets

async def run_chat():
    uri = "ws://127.0.0.1:8000/ws"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({
            "type": "command",
            "id": "msg_001",
            "command": "send_message",
            "payload": {
                "content": "给我一个发布流程模板",
                "session_id": "api",
                "max_turns": 4
            }
        }))

        while True:
            msg = json.loads(await ws.recv())
            if msg["type"] == "event":
                print("[event]", msg.get("event_type"), msg.get("data"))
            elif msg["type"] == "response":
                print("[response]", msg.get("payload"))
                break
            elif msg["type"] == "error":
                print("[error]", msg.get("message"))
                break

asyncio.run(run_chat())
```

### 10.2 JavaScript（WebSocket）

```javascript
const ws = new WebSocket("ws://127.0.0.1:8000/ws");

ws.onopen = () => {
  ws.send(JSON.stringify({
    type: "command",
    id: "msg_001",
    command: "send_message",
    payload: {
      content: "你好，帮我规划一个需求评审流程",
      session_id: "api",
      max_turns: 4
    }
  }));
};

ws.onmessage = (evt) => {
  const msg = JSON.parse(evt.data);
  if (msg.type === "event") {
    console.log("[event]", msg.event_type, msg.data);
    return;
  }
  if (msg.type === "response") {
    console.log("[response]", msg.payload);
    return;
  }
  if (msg.type === "error") {
    console.error("[error]", msg.message);
  }
};
```

## 11. 常见问题（FAQ）

Q1：为什么我收不到 `event`，只收到 `response`？

- 先确认走的是 WS，不是 HTTP `POST /api/v1/messages`
- 再确认命令是 `send_message`
- 检查前端是否把 `type=event` 过滤掉了

Q2：为什么审批命令返回失败？

- `request_id` 必须来自当前连接收到的 `permission_request`
- `session_id` 必填，且要与该审批请求所属会话一致

Q3：会话切换后消息不对？

- 建议流程：`switch_session` 后再 `get_session` 同步一次前端状态

## 12. 生产化前必做清单

- 增加鉴权与授权（JWT / 网关 / 内网 ACL）
- 收敛 CORS 白名单，禁止 `*`
- 对高风险工具启用严格审批和审计
- 给 WS 接入层添加限流与连接数保护
- 对 `event_type/session_id/command_id` 做结构化日志

相关说明见：[当前问题.md](当前问题.md)
