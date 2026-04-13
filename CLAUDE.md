# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GGbot is a minimal CLI/TUI agent inspired by Claude Code, built in Python. It's a multi-provider LLM agent with tool calling capabilities, workspace sandboxing, and transcript logging.

## Development Environment

### Setup with uv (recommended)
```bash
uv venv .venv
source .venv/bin/activate  # or .\.venv\Scripts\Activate.ps1 on Windows
uv sync --extra dev
```

### Setup with pip
```bash
python -m pip install -e .[dev]
```

### Common Development Commands
- Run tests: `uv run pytest` or `pytest`
- Run specific test: `uv run pytest tests/test_query_loop_tool_calls.py -v`
- Run with keyword filter: `uv run pytest -k "query_loop" -vv`
- Run only failed tests: `uv run pytest --lf`
- Debug mode: `uv run pytest --pdb`

### GGbot CLI Commands
- `uv run ggbot --help` - Show help
- `uv run ggbot chat "your question"` - One-off chat
- `uv run ggbot repl` - Interactive REPL
- `uv run ggbot tui` - Terminal UI
- `uv run ggbot log --follow --events` - View live transcript with events
- `uv run ggbot --debug repl` - REPL with rich tracebacks

## Architecture

### Core Components
1. **CLI Entry** (`ggbot/cli.py`): Registers built-in tools, creates sessions, initializes prompt manager
2. **Agent Loop** (`ggbot/core/agent_loop.py`): Main query loop with tool execution, budget limits, and transcript recording
3. **Provider Layer** (`ggbot/providers/litellm_client.py`): LiteLLM-based multi-provider client
4. **Tool System** (`ggbot/tools/`): Tool registry and built-in tools (file, shell, HTTP, workspace, jobs, status)
5. **Prompt System** (`ggbot/prompts/`): Prompt management with configurable profiles
6. **Configuration** (`ggbot/core/config.py`): Loads from env > .env > TOML > defaults
7. **Transcript System** (`ggbot/core/transcript.py`): JSONL event logging for session replay

### Key Architectural Patterns
- **Tool Context Injection**: Tools can accept `ctx: ToolContext` parameter for emitting status/tool_stream events
- **Message Sequence Validation**: Agent loop auto-heals missing tool messages and sanitizes orphan tool messages
- **Workspace Sandbox**: All file operations restricted to `workspace_root` directory
- **Tool Budget Limits**: Prevents runaway tool calls with `max_tool_calls`, `max_tool_calls_per_tool`, `max_tool_calls_same_args`

## Configuration Priority
1. Command-line arguments (highest)
2. Environment variables (from shell or `.env` files)
3. TOML configuration (`.ggbot/config.toml`)
4. Default values (lowest)

### Essential Environment Variables
- `OPENAI_MODEL`: Model name for LiteLLM (e.g., `gpt-4.1-mini`, `claude-3-5-sonnet-20241022`)
- `OPENAI_API_KEY`: API key for OpenAI-compatible providers
- `OPENAI_BASE_URL`: Base URL (default: `https://api.openai.com/v1`)
- `GGBOT_THINKING_ENABLED`: Enable thinking/reasoning output (default: `false`)

## Thinking Functionality
When `GGBOT_THINKING_ENABLED=true`, GGbot extracts and displays model reasoning:
- Thinking messages use `role="thinking"` in internal types
- For API compatibility (e.g., DeepSeek), thinking messages are converted to `system` role with `[Thinking]` prefix
- Supported formats: `思考：...\n\n回答：...`, `Thinking: ...\n\nAnswer: ...`, `<thinking>...</thinking><answer>...</answer>`

## Adding New Tools
1. Create tool module in `ggbot/tools/` or add to existing module
2. Define Pydantic input model and tool function:
   ```python
   from pydantic import BaseModel
   from ggbot.tools.registry import tool
   
   class MyArgs(BaseModel):
       param: str
   
   @tool(name="my_tool", description="Does something", input_model=MyArgs)
   def my_tool(args: MyArgs) -> str:
       return f"Result: {args.param}"
   ```
3. For streaming/status events, use `ctx: ToolContext` parameter
4. Register in `ggbot/cli.py` `_register_builtin_tools()`
5. Add tests in `tests/`

## Testing Patterns
- Use `tmp_path` fixture for isolated test directories
- Mock network calls with `httpx.MockTransport`
- Mock LiteLLM with `monkeypatch.setattr("litellm.completion", ...)`
- Test tool execution with `ToolRegistry` and mock clients
- Check transcript events for correctness

## Transcript System
- JSONL format with event types: `model_message`, `tool_call`, `tool_result`, `tool_stream`, `status`, `provider_error`
- Session types: `chat`, `repl`, `tui` (each has default transcript file)
- Resume sessions with `--resume` flag
- View with `ggbot log --follow --events`

## Common Development Tasks

### Running Specific Tests
- Tool-related: `uv run pytest -k "tool" -vv`
- Query loop: `uv run pytest -k "query_loop" -vv`
- Configuration: `uv run pytest -k "config" -vv`
- Async tools: `uv run pytest -k "async" -vv`

### Debugging
- Use `--debug` flag for rich tracebacks: `uv run ggbot --debug repl`
- Check transcript: `uv run ggbot log --follow --events`
- Test thinking extraction: `uv run pytest tests/test_thinking.py -v`

### Configuration Testing
- Test config loading: `uv run pytest tests/test_config_load.py -v`
- Integration test: `uv run pytest tests/test_config_integration.py -v`

## Critical Considerations
1. **API Compatibility**: Some providers (e.g., DeepSeek) don't support `role="thinking"` - converted to `system` role
2. **Tool Message Ordering**: Assistant `tool_calls` must be immediately followed by corresponding `tool` messages
3. **Transcript Compatibility**: Changes must not break reading of existing JSONL transcripts
4. **Workspace Safety**: File tools must respect `workspace_root` sandbox boundary
5. **Tool Budgets**: Prevent infinite loops with appropriate `max_tool_calls*` settings

## References
- `README.md` - Quick start and basic usage
- `CONFIGURATION.md` - Detailed configuration guide
- `doc/architecture.md` - Comprehensive architecture documentation
- `doc/development.md` - Development guidelines
- `doc/tests.md` - Pytest usage reference
- `.github/copilot-instructions.md` - Additional project guidelines