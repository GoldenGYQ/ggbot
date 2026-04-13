# 架构（Architecture）

**文档分级：A（只给项目成员｜内部）**

## 总览

GGbot 是一个最小化的 CLI/TUI Agent：
- 输入：用户自然语言
- 输出：模型文本 + 工具调用（tool calls）
- 关键保证：
  - 工具只能在 workspace_root 沙箱内读写（见 `ggbot/core/permissions.py`）
  - transcript 使用 JSONL 事件流落盘，可复盘/恢复（见 `ggbot/core/transcript.py`）
  - query loop 保证 tool_call/tool_result 的时序合法，并提供自动修复（见 `ggbot/core/agent_loop.py`）

## 模块分层

- CLI 入口：`ggbot/cli.py`
  - 注册内置工具
  - 创建 transcript/session
  - 调用 query loop（run_query）

- 核心循环：`ggbot/core/agent_loop.py`
  - 维护 messages 列表（OpenAI-style chat messages）
  - 调用 provider client（LiteLLMClient）进行流式生成
  - 解析工具调用并执行工具
  - 记录事件到 transcript（tool_call/tool_result/status/tool_stream/provider_error…）
  - 工具调用预算（tool budget）限制重复/失控调用

- Provider（LLM 调用）：`ggbot/providers/litellm_client.py`
  - 统一通过 LiteLLM 适配多家 provider
  - 产出 assistant final：content + tool_calls
  - 错误统一包装为 `ProviderError`

- 工具系统：`ggbot/tools/`
  - `registry.py`：工具注册/Schema 导出/执行
  - `context.py`：ToolContext 注入（用于工具向 transcript 发事件）
  - 各类工具模块：文件、shell、网络、job、workspace、status…

- 会话与持久化：`ggbot/core/sessions.py`、`ggbot/core/session_meta.py`
  - session id 与元信息
  - 与 transcript 文件的映射

## 数据流（一次 turn）

1) 用户输入追加到 messages，并写入 transcript：`type=model_message`
2) 调用 provider：`client.stream_and_collect(messages, tools=registry.openai_tools())`
3) provider 流式输出文本：可通过 `on_text_delta` 打印到 CLI/TUI
4) provider 返回 tool_calls：写入 transcript（assistant 的 model_message）
5) 对每个 tool_call：
   - 记录 `type=tool_call` 事件
   - 执行工具（带 ToolContext）
   - 追加 tool message 到 messages（role=tool, tool_call_id=...）
   - 记录 `type=tool_result` 事件
6) 若 assistant 没有 tool_calls：本轮结束

## Transcript 事件类型（常用）

- `model_message`：所有 chat message（system/user/assistant/tool）
- `tool_call`：工具调用（解析后的 arguments + 原始 arguments）
- `tool_result`：工具返回（长度、是否 error、是否 auto_healed 等）
- `tool_stream`：工具执行过程中的增量输出（例如 `shell_stream`）
- `status`：工具/运行时状态更新（例如 `status_update`）
- `provider_error`：provider 调用失败/异常

CLI 可用：`ggbot log --follow --events` 实时查看这些事件。

## 工具约定

### Schema

当前工具 schema 输出为 OpenAI tool schema（`ToolSpec.as_openai_tool()`）。
注意：这只是 schema 形式；provider 侧实际是 LiteLLM。

### ToolContext 注入

工具函数可以声明两种签名：
- `def tool_name(args: ArgsModel) -> str`
- `def tool_name(ctx: ToolContext, args: ArgsModel) -> str`

当声明了 `ctx: ToolContext`，运行时会注入上下文，可用于：
- `ctx.emit("status", {...})`：写 status 事件
- `ctx.emit("tool_stream", {...})`：写 tool_stream 事件

### Budget（防失控）

`ToolLimits`：
- `max_tool_calls`
- `max_tool_calls_per_tool`
- `max_tool_calls_same_args`

用于阻止模型在 tool_calls 上进入“重复调用同一工具/同参”的死循环。

## 兼容性注意

- 多数 OpenAI-compatible provider 要求：assistant 的 tool_calls 必须紧跟对应的 tool messages。
- `agent_loop` 内置两段修复逻辑：
  - 自动补齐缺失的 tool messages（auto-heal）
  - 孤儿 tool messages 转 system（sanitize）

改动 query loop 或 transcript 格式时，必须保证：
- 恢复逻辑仍能读旧 JSONL
- tool_call/tool_result 的顺序不被破坏
