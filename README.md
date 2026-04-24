# GGbot

一个以 Python 为核心的本地 Agent Runtime。  
它把「模型对话能力」和「工程执行能力（文件、Shell、网页等工具）」放在同一条运行时主链路里，支持：

- 本地交互入口：CLI / REPL / TUI（终端内直接使用）
- 对外服务接口：FastAPI + WebSocket（供前端/业务系统接入）
- transcript（JSONL）可追溯日志
- 会话级上下文与权限审批（重点针对 `shell_run`）

## 3 分钟本地启动

### 1) 安装依赖（推荐 `uv`）

Windows（PowerShell）：

```powershell
uv venv .venv
.\.venv\Scripts\Activate.ps1
uv sync --extra dev
```

macOS / Linux：

```bash
uv venv .venv
source .venv/bin/activate
uv sync --extra dev
```

### 2) 配置模型（最小）

在仓库根目录创建 `.env`：

（你也可以直接从 `./.env.example` 复制一份。）

```
OPENAI_MODEL=gpt-4.1-mini
OPENAI_API_KEY=sk-xxxx
```

### 3) 运行

```bash
uv run ggbot --help
uv run ggbot repl
uv run ggbot tui
uv run ggbot chat "你好"
```

## 本地 API 启动

```bash
uv run ggbot api --host 127.0.0.1 --port 8000
```

启动后可访问：

- OpenAPI 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/api/v1/health`
- WebSocket：`ws://127.0.0.1:8000/ws`

## API 最小调用示例

当前主链路是 **WebSocket 命令式调用**（`send_message`）。  
`POST /api/v1/messages` 已在代码中标记为 deprecated 并关闭。

### WebSocket：发送消息命令

发送：

```json
{
  "type": "command",
  "id": "cmd_1",
  "command": "send_message",
  "payload": {
    "content": "帮我列一个今天的开发计划",
    "max_turns": 4,
    "thinking_enabled": false
  }
}
```

你会收到两类消息：

- `type=event`：过程事件（`assistant_delta` / `tool_call` / `tool_result` / `permission_request` 等）
- `type=response`：命令完成响应

### REST：可用于管理接口

```bash
curl http://127.0.0.1:8000/api/v1/sessions
curl http://127.0.0.1:8000/api/v1/tools
```

## 运行时日志（Transcript）

GGbot 把 transcript 作为统一事实源（JSONL）：

- 默认目录：`<workspace>/.ggbot/transcripts/`
- 每个会话一个文件：`<session_id>.jsonl`
- 可用命令查看：

```bash
uv run ggbot log
uv run ggbot log --follow
uv run ggbot log --follow --events
```

## 关键环境变量

- `OPENAI_MODEL`：模型名（LiteLLM `model`）
- `OPENAI_API_KEY`：模型 API Key
- `OPENAI_BASE_URL`：模型 API 地址（默认 `https://api.openai.com/v1`）
- `GGBOT_WORKSPACE_ROOT`：工作区根目录
- `GGBOT_TRANSCRIPT_DIR`：transcript 存储目录
- `GGBOT_PROMPT_PROFILE`：提示词 profile
- `GGBOT_PROMPT_DIR`：提示词目录

## 文档导航（先看这几个）

- 总览索引：[doc/README.md](doc/README.md)
- API 使用手册：[doc/API_README.md](doc/API_README.md)
- 架构设计：[doc/architecture.md](doc/architecture.md)
- 开发指南：[doc/development.md](doc/development.md)
- 配置说明：[doc/configuration.md](doc/configuration.md)
- 当前问题清单：[doc/当前问题.md](doc/当前问题.md)
- 贡献说明：[doc/contributing.md](doc/contributing.md)

## 安全提示（当前状态）

当前版本默认面向本地开发环境，生产部署前请先完成：

- API 鉴权与授权
- CORS 收敛
- 高风险工具（如 `shell_run`）默认拒绝未认证请求
