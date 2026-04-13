# GGBot (Python MVP)

A minimal, Claude-Code-inspired CLI agent.

文档分级：A（只给项目成员｜内部）
## Quick Start (uv, recommended)

From repo root:

### Windows (PowerShell)

```powershell
uv venv .venv
.\.venv\Scripts\Activate.ps1
uv sync --extra dev
```

If activation is blocked by execution policy:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### macOS / Linux (bash/zsh)

```bash
uv venv .venv
source .venv/bin/activate
uv sync --extra dev
```

Run commands via `uv run` (or run directly after activation):

- `uv run ggbot --help`
- `uv run ggbot --debug repl`
- `uv run ggbot chat "hello"`
- `uv run ggbot repl`
- `uv run ggbot tui`
- `uv run pytest`

## Install (pip editable, alternative)

From repo root:

- `python -m pip install -e .[dev]`

## Run

- `ggbot --help`
- `ggbot --debug repl` (pretty tracebacks)
- `ggbot chat "hello"` 
- `ggbot repl`
- `ggbot tui`
- `ggbot log` （print the recent logs）
- `ggbot log --follow`(view transcript log in terminal)

In REPL, you can create project folders inside the current workspace via:

- `/workspace <path>`
- `/workspace_ls [path]` (list files/dirs under workspace, default current root)

In TUI:

- `/clear` asks for confirmation, then clears current session history.
- `/clear-screen` only clears visible screen output.

Log viewer examples:

- `ggbot log` (open the most recent session log)
- `ggbot log --session repl`
- `ggbot log --tail 100`
- `ggbot log --follow` (real-time monitoring)
- `ggbot log --follow --events` (show runtime events like tool_call/tool_result)

## Env

GGBot 会按优先级读取配置：

1) 真实环境变量
2) dotenv 文件：`./.env`、`./.ggbot/.env`
3) TOML 配置：`./.ggbot/config.toml`

最常用的是把 Key 放到 `.env` 或 `config.toml`。

仓库里也提供了一个可直接复制的示例文件：`./.env.example`。

### 环境变量

- `OPENAI_MODEL`
	- 作为 LiteLLM 的 `model` 默认值（例如 OpenAI、Anthropic、Gemini、各类网关/代理等）。
	- 具体模型命名规则以 LiteLLM 文档为准（不同 provider 的前缀/命名不同）。
- `OPENAI_API_KEY`
	- 可选：作为 LiteLLM 的 `api_key` 默认值（对 OpenAI / OpenAI-compatible 网关通常需要）。
	- 如果你使用的是其他 provider（例如 Anthropic/Gemini/Azure 等），通常需要设置该 provider 对应的环境变量（由 LiteLLM 读取），此时可以不设置 `OPENAI_API_KEY`。
- `OPENAI_BASE_URL`（默认：`https://api.openai.com/v1`）
	- 可选：作为 LiteLLM 的 `api_base` 默认值（常用于 OpenAI-compatible 网关）。
- `GGBOT_WORKSPACE_ROOT`（默认：当前工作目录）

Transcript:
- `GGBOT_TRANSCRIPT_DIR` (default: `.ggbot/transcripts` under workspace)

Prompt Engineering:
- `GGBOT_PROMPT_PROFILE` (default: `default`)
- `GGBOT_PROMPT_DIR` (default: `./.ggbot/prompts`)

### 例子：.env

在仓库根目录创建 `./.env`：

（你也可以直接从 `./.env.example` 复制一份。）

```
OPENAI_MODEL=gpt-4.1-mini
OPENAI_API_KEY=sk-xxxx
```

### 例子：.ggbot/config.toml

创建 `./.ggbot/config.toml`：

```toml
[openai]
# 这里的 key 名沿用历史/兼容命名：作为 LiteLLM 的默认 model/api_base/api_key。
# 仅当你使用 OpenAI/OpenAI-compatible 网关时通常需要 api_key/base_url。
api_key = "sk-xxxx"
base_url = "https://api.openai.com/v1"
model = "gpt-4.1-mini"

[ggbot]
max_turns = 8

[prompt]
# profile file: ./.ggbot/prompts/<profile>.md
profile = "default"
# optional custom prompt directory
dir = "./.ggbot/prompts"

[shell]
confirm = true
timeout_ms = 30000
max_output_chars = 30000
```

## Docs (internal)

- Start here: [doc/README.md](doc/README.md)
- Architecture: [doc/architecture.md](doc/architecture.md)
- Development: [doc/development.md](doc/development.md)
- Configuration & Ops: [doc/configuration.md](doc/configuration.md)
- Security: [doc/security.md](doc/security.md)
- Troubleshooting: [doc/troubleshooting.md](doc/troubleshooting.md)
- Contributing: [doc/contributing.md](doc/contributing.md)
- Testing quickref: [doc/tests.md](doc/tests.md)
