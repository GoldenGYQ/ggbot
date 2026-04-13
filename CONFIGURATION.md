# GGbot Configuration Guide

GGbot supports multiple configuration sources with the following priority order (highest to lowest):

1. **Command-line arguments** (e.g., `--thinking`, `--max-turns`)
2. **Environment variables** (from `.env` files or shell)
3. **TOML configuration file** (`.ggbot/config.toml`)
4. **Default values**

## Quick Start

1. Copy `.env.example` to `.env` and customize
2. Copy `.ggbot/config.toml.example` to `.ggbot/config.toml` and customize
3. Set your API keys and preferences

## Configuration Options

### LLM Configuration (via LiteLLM)

GGbot uses [LiteLLM](https://github.com/BerriAI/liteLLM) for multi-provider support.

| Variable | TOML Path | Default | Description |
|----------|-----------|---------|-------------|
| `OPENAI_MODEL` | `openai.model` | `"gpt-4.1-mini"` | Model name passed to LiteLLM |
| `OPENAI_API_KEY` | `openai.api_key` | `None` | API key for OpenAI-compatible providers |
| `OPENAI_BASE_URL` | `openai.base_url` | `"https://api.openai.com/v1"` | Base URL for API calls |

**Provider-specific notes:**
- **OpenAI**: Set `OPENAI_API_KEY` and optionally `OPENAI_BASE_URL`
- **Anthropic**: Set `ANTHROPIC_API_KEY` in `.env`
- **Google Gemini**: Set `GEMINI_API_KEY` in `.env`
- **Azure OpenAI**: Set `AZURE_API_KEY` and `AZURE_API_BASE` in `.env`
- **Local Ollama**: Set `OPENAI_BASE_URL=http://localhost:11434` and `OPENAI_API_KEY=ollama`

### Core GGbot Behavior

| Variable | TOML Path | Default | Description |
|----------|-----------|---------|-------------|
| `GGBOT_MAX_TURNS` | `ggbot.max_turns` | `8` | Maximum conversation turns per query |
| `GGBOT_MAX_TOOL_CALLS` | `ggbot.max_tool_calls` | `30` | Maximum total tool calls |
| `GGBOT_MAX_TOOL_CALLS_PER_TOOL` | `ggbot.max_tool_calls_per_tool` | `20` | Maximum calls per individual tool |
| `GGBOT_MAX_TOOL_CALLS_SAME_ARGS` | `ggbot.max_tool_calls_same_args` | `3` | Maximum calls with identical arguments |
| `GGBOT_THINKING_ENABLED` | `ggbot.thinking_enabled` | `false` | Enable thinking/reasoning output |

### Workspace & File System

| Variable | TOML Path | Default | Description |
|----------|-----------|---------|-------------|
| `GGBOT_WORKSPACE_ROOT` | `ggbot.workspace_root` | Current directory | Sandbox boundary for file operations |
| `GGBOT_TRANSCRIPT_DIR` | `transcript.dir` | `<workspace>/.ggbot/transcripts` | Transcript storage directory |

### Prompt Engineering

| Variable | TOML Path | Default | Description |
|----------|-----------|---------|-------------|
| `GGBOT_PROMPT_PROFILE` | `prompt.profile` | `"default"` | Prompt profile name |
| `GGBOT_PROMPT_DIR` | `prompt.dir` | `<workspace>/.ggbot/prompts` | Custom prompt directory |

### Shell Tool Safety

| Variable | TOML Path | Default | Description |
|----------|-----------|---------|-------------|
| `GGBOT_SHELL_CONFIRM` | `shell.confirm` | `true` | Require confirmation for shell commands |
| `GGBOT_SHELL_TIMEOUT_MS` | `shell.timeout_ms` | `30000` | Maximum execution time (ms) |
| `GGBOT_SHELL_MAX_OUTPUT_CHARS` | `shell.max_output_chars` | `30000` | Maximum output size (chars) |

## Thinking Functionality

The thinking feature allows GGbot to extract and display the model's reasoning process.

### Enabling Thinking

1. **Via environment variable**: `GGBOT_THINKING_ENABLED=true`
2. **Via config file**: `thinking_enabled = true` in `[ggbot]` section
3. **Via command line**: `ggbot chat "question" --thinking`

### How It Works

1. When thinking is enabled, the system prompt includes instructions for structured thinking output
2. The model outputs thinking in a structured format (e.g., "思考：...\n\n回答：...")
3. GGbot extracts the thinking content and displays it separately
4. Thinking messages are recorded in transcripts and displayed with special formatting

### Supported Formats

GGbot recognizes multiple thinking formats:

```text
# Chinese format (recommended)
思考：<reasoning process>
回答：<final answer>

# English format
Thinking: <reasoning process>
Answer: <final answer>

# XML format
<thinking>reasoning</thinking>
<answer>final answer</answer>
```

## Configuration Examples

### Example 1: Basic OpenAI Setup

**.env:**
```bash
OPENAI_MODEL=gpt-4
OPENAI_API_KEY=sk-your-key-here
```

### Example 2: Claude with Thinking Enabled

**.env:**
```bash
OPENAI_MODEL=claude-3-5-sonnet-20241022
ANTHROPIC_API_KEY=your-anthropic-key
GGBOT_THINKING_ENABLED=true
```

**.ggbot/config.toml:**
```toml
[openai]
model = "claude-3-5-sonnet-20241022"

[ggbot]
thinking_enabled = true
```

### Example 3: Local Ollama

**.env:**
```bash
OPENAI_MODEL=ollama/llama3.2
OPENAI_BASE_URL=http://localhost:11434
OPENAI_API_KEY=ollama
GGBOT_THINKING_ENABLED=true
```

### Example 4: Strict Safety Settings

**.ggbot/config.toml:**
```toml
[ggbot]
max_tool_calls = 10
max_tool_calls_per_tool = 5
max_tool_calls_same_args = 2

[shell]
confirm = true
timeout_ms = 10000
max_output_chars = 10000
```

## Command-line Overrides

All configuration options can be overridden via command-line arguments:

```bash
# One-off chat with thinking enabled
ggbot chat "Write a function" --thinking --max-turns 5

# REPL mode with custom workspace
ggbot repl --workspace-root ./my-project --thinking

# TUI mode with thinking
ggbot tui --thinking
```

## Session Management

GGbot supports three session types:

1. **chat**: One-off conversations (transcript: `chat.jsonl`)
2. **repl**: Interactive REPL mode (transcript: `repl.jsonl`)
3. **tui**: Terminal UI with visual features (transcript: `tui.jsonl`)

Each session type has its own default transcript file, but you can resume any session using the `--resume` flag.

## Troubleshooting

### Configuration Not Working

1. Check priority order: command line > environment > config file > defaults
2. Verify file locations: `.env` in repo root or `.ggbot/.env`
3. Check for syntax errors in `.env` or `config.toml`

### Thinking Not Showing

1. Ensure `GGBOT_THINKING_ENABLED=true` is set
2. Check that the model follows the thinking format in prompts
3. Try with a model known to support reasoning (Claude, GPT-4, o1)

### API Connection Issues

1. Verify API keys are correctly set
2. Check network connectivity
3. For local models, ensure the service is running
4. Review LiteLLM documentation for provider-specific requirements

## Advanced Configuration

### Custom Prompts

Create custom prompt profiles in `.ggbot/prompts/`:

```bash
# Create a custom profile
mkdir -p .ggbot/prompts
echo "# My Custom Prompt\nBe concise and technical." > .ggbot/prompts/technical.md

# Use the custom profile
export GGBOT_PROMPT_PROFILE=technical
```

### Transcript Management

Transcripts are stored as JSONL files. You can:
- View transcripts: `ggbot log --session <session_id>`
- Follow live: `ggbot log --session <session_id> --follow`
- Clear a session: Use `/clear` command in TUI or REPL

### Turn Tracking and Display

GGbot tracks conversation turns and displays them in multiple places:

1. **TUI Status Bar**: Shows current conversation turn count in format `T:<user_turns>/<max_turns> C:<current_turn>/<max_turns>`
   - `T`: Total user turns in the session
   - `C`: Current conversation turn (resets with each new query)

2. **Log Events**: When using `ggbot log --follow --events`, you can see turn events:
   - `turn_info`: Initial turn configuration
   - `turn_update`: Current turn progress
   - `turn_complete`: Final turn usage summary

3. **Transcript Events**: Turn events are recorded in the transcript JSONL:
   ```json
   {"ts_ms": 1234567890, "type": "turn_update", "data": {"current_turn": 2, "max_turns": 8}}
   {"ts_ms": 1234567891, "type": "turn_complete", "data": {"turns_used": 3, "max_turns": 8, "completed": true}}
   ```

4. **Configuration**: The maximum turns is controlled by `GGBOT_MAX_TURNS` (default: 8)

### Tool Call Limits

Adjust tool call limits for specific use cases:
- **Development tasks**: Higher limits (defaults are fine)
- **Production/safety**: Lower limits to prevent runaway processes
- **Testing**: Minimal limits to catch infinite loops early