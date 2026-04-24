# 配置与运行（Configuration & Ops）

**文档分级：A（只给项目成员｜内部）**

## 配置优先级

GGbot 按优先级读取配置：

1) 真实环境变量（export/set 的 env）
2) dotenv：`./.env`、`./.ggbot/.env`
3) TOML：`./.ggbot/config.toml`（只填“未被 env 设置”的值）
4) 代码默认值

对应实现：`ggbot/app/config.py`。

## LLM / LiteLLM

本项目通过 LiteLLM 调用模型（见 `ggbot/providers/litellm_client.py`）。

### 关键点

- GGbot 当前仍沿用 `OPENAI_*` 变量名作为“默认值”传给 LiteLLM：
  - `OPENAI_MODEL` -> LiteLLM `model`
  - `OPENAI_API_KEY` -> LiteLLM `api_key`
  - `OPENAI_BASE_URL` -> LiteLLM `api_base`

- 但这不意味着“只能 OpenAI”。
  - 你可以把 `OPENAI_MODEL` 设置为 LiteLLM 支持的任意模型标识。
  - provider 需要的凭据通常由 LiteLLM 从环境变量读取（例如 `ANTHROPIC_API_KEY`、`GEMINI_API_KEY` 等）。

### 最小示例（OpenAI / OpenAI-compatible）

`.env`：

```
OPENAI_MODEL=gpt-4.1-mini
OPENAI_API_KEY=sk-xxxx
# OPENAI_BASE_URL=https://api.openai.com/v1
```

### TOML 示例

`./.ggbot/config.toml`：

```toml
[openai]
# 作为 LiteLLM 的默认 model/api_base/api_key
model = "gpt-4.1-mini"
api_key = "sk-xxxx"
base_url = "https://api.openai.com/v1"

[ggbot]
max_turns = 8
max_tool_calls = 30
max_tool_calls_per_tool = 12
max_tool_calls_same_args = 3

[transcript]
dir = ".ggbot/transcripts"

[shell]
confirm = true
timeout_ms = 30000
max_output_chars = 30000
```

## Workspace Root（沙箱根目录）

- `GGBOT_WORKSPACE_ROOT`：默认当前工作目录
- 所有文件工具与 shell 工具都必须遵守 workspace sandbox（见 `ggbot/workspace/permissions.py`）

建议：开发时把 workspace root 指向一个专用目录，避免误操作。

## Transcript（会话记录）

- `GGBOT_TRANSCRIPT_DIR`：默认 `<workspace_root>/.ggbot/transcripts`
- 文件格式：`*.jsonl`，每行一个 JSON 事件

查看：
- `ggbot log`：查看最近会话
- `ggbot log --follow --events`：实时跟踪并显示事件

## Tool budget（防止失控）

环境变量：
- `GGBOT_MAX_TOOL_CALLS`
- `GGBOT_MAX_TOOL_CALLS_PER_TOOL`
- `GGBOT_MAX_TOOL_CALLS_SAME_ARGS`

建议：保持默认即可；当出现“模型重复调用工具”时可临时调小阈值用于止血。

## Shell safety

- `GGBOT_SHELL_CONFIRM`：默认 true（执行前需要确认）
- `GGBOT_SHELL_TIMEOUT_MS`
- `GGBOT_SHELL_MAX_OUTPUT_CHARS`

注意：shell 工具属于高风险工具，默认启用确认是必须的。
