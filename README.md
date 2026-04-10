# GGBot (Python MVP)

A minimal, Claude-Code-inspired CLI agent.

## Quick Start (uv, recommended)

From repo root:

```powershell
uv venv .venv
.\.venv\Scripts\Activate.ps1
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

## Env

GGBot 会按优先级读取配置：

1) 真实环境变量
2) dotenv 文件：`./.env`、`./.ggbot/.env`
3) TOML 配置：`./.ggbot/config.toml`

最常用的是把 Key 放到 `.env` 或 `config.toml`。

仓库里也提供了一个可直接复制的示例文件：`./.env.example`。

### 环境变量

- `OPENAI_BASE_URL`（默认：`https://api.openai.com/v1`）
- `OPENAI_API_KEY`（必填）
- `OPENAI_MODEL`
- `GGBOT_WORKSPACE_ROOT`（默认：当前工作目录）

Transcript:
- `GGBOT_TRANSCRIPT_DIR` (default: `.ggbot/transcripts` under workspace)

### 例子：.env

在仓库根目录创建 `./.env`：

（你也可以直接从 `./.env.example` 复制一份。）

```
OPENAI_API_KEY=sk-xxxx
OPENAI_MODEL=gpt-4.1-mini
```

### 例子：.ggbot/config.toml

创建 `./.ggbot/config.toml`：

```toml
[openai]
api_key = "sk-xxxx"
base_url = "https://api.openai.com/v1"
model = "gpt-4.1-mini"

[ggbot]
max_turns = 8

[shell]
confirm = true
timeout_ms = 30000
max_output_chars = 30000
```
