# 故障排查（Troubleshooting）

**文档分级：A（只给项目成员｜内部）**

## 先看 transcript（最有效）

- 查看最近会话：`ggbot log`
- 实时跟踪（含事件）：`ggbot log --follow --events`

重点事件：
- `provider_error`：provider 调用失败
- `tool_call` / `tool_result`：工具调用与返回
- `status` / `tool_stream`：运行过程状态与增量输出

## 常见问题

### 1) 运行就报 provider_error

排查方向：
- 模型名是否正确（`OPENAI_MODEL`/TOML 的 `openai.model`）
- provider 凭据是否齐全（OpenAI-compatible 用 `OPENAI_API_KEY`；其他 provider 依 LiteLLM 要求设置对应 env）
- 是否需要 `OPENAI_BASE_URL`（仅 OpenAI-compatible 网关常用）

### 2) 模型一直重复调用同一个工具（停不下来）

现象：`tool_call` 事件里同名工具反复出现，参数也相同。

止血策略：
- 降低 budget：
  - `GGBOT_MAX_TOOL_CALLS`
  - `GGBOT_MAX_TOOL_CALLS_PER_TOOL`
  - `GGBOT_MAX_TOOL_CALLS_SAME_ARGS`

定位策略：
- 查看每次 tool_result 的内容是否让模型误解（例如空输出/错误信息不清楚）
- 检查工具是否返回了“下一步该怎么做”的明确提示

### 3) 工具输出太长，影响模型表现

策略：
- 工具侧截断输出（已存在 shell max_output_chars）
- 在 tool_result 中优先返回摘要 + 引导（例如：告诉模型输出已截断，建议下一步用更精确参数重试）

### 4) 历史会话恢复后报错（tool message sequence）

背景：很多 OpenAI-compatible provider 要求 tool message 顺序严格。

现象：provider 报 400 或提示 tool_call/tool_result 不匹配。

项目内置修复：
- 缺失 tool responses：自动补齐（auto-heal）
- 孤儿 tool message：转 system（sanitize）

如果仍失败：
- 用 `ggbot log --events` 检查最后一次 tool_calls 是否都对应 tool_result

### 5) TUI 显示异常 / 卡住

建议：
- 先用 CLI 跑同样的输入，确认是否是 TUI 展示层问题
- 若涉及 shell_stream：关注是否持续产生 `tool_stream` 事件

## 收集信息（发给维护者）

最小复现包建议包含：
- 触发问题的命令（例如 `uv run ggbot repl`）
- 触发问题的输入文本
- 对应 session 的 transcript（脱敏后）
- 环境信息：OS、Python 版本、uv 版本、关键 env（不要包含密钥）
