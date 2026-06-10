# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

GGbot is a minimal CLI/TUI agent inspired by Codex, built in Python. It's a multi-provider LLM agent with tool calling capabilities, workspace sandboxing, and transcript logging.

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

### Project Dependencies
Key dependencies (see `pyproject.toml`):
- **Core**: `pydantic`, `pydantic-settings`, `httpx`, `litellm`, `typer`
- **UI**: `textual` (TUI framework)
- **Web**: `readability-lxml`, `ddgs` (DuckDuckGo search)
- **Dev**: `pytest`

### Common Development Commands
- Run all tests: `uv run pytest` or `pytest`
- Run specific test file: `uv run pytest tests/test_query_loop_tool_calls.py -v`
- Run tests by keyword: `uv run pytest -k "query_loop" -vv`
- Run only failed tests: `uv run pytest --lf`
- Debug mode: `uv run pytest --pdb`
- Show test durations: `uv run pytest --durations=10`
- Run with verbose output: `uv run pytest -vv`
- Skip output capture: `uv run pytest -s` (for debugging)

### GGbot CLI Commands
- `uv run ggbot --help` - Show help
- `uv run ggbot chat "your question"` - One-off chat
- `uv run ggbot repl` - Interactive REPL
- `uv run ggbot tui` - Terminal UI
- `uv run ggbot log --follow --events` - View live transcript with events
- `uv run ggbot --debug repl` - REPL with rich tracebacks
- `uv run ggbot log --session repl --tail 100` - View specific session logs

## Architecture

### Core Components
1. **CLI Entry** (`ggbot/cli.py`): Registers built-in tools, creates sessions, initializes prompt manager
2. **Agent Loop** (`ggbot/core/agent_loop.py`): Main query loop with tool execution, budget limits, and transcript recording
3. **Provider Layer** (`ggbot/providers/litellm_client.py`): LiteLLM-based multi-provider client
4. **Tool System** (`ggbot/tools/`): Tool registry and built-in tools (file, shell, HTTP, workspace, jobs, status)
5. **Prompt System** (`ggbot/prompts/`): Prompt management with configurable profiles
6. **Configuration** (`ggbot/core/config.py`): Loads from env > .env > TOML > defaults
7. **Transcript System** (`ggbot/core/transcript.py`): JSONL event logging for session replay
8. **Runtime Events** (`ggbot/core/events.py`, `ggbot/core/runtime_events.py`): Event definitions and runtime event handling
9. **Transport Protocol** (`ggbot/core/transport_protocol.py`): Versioned event envelopes for transport layers
10. **Session Management** (`ggbot/core/session_store.py`, `ggbot/core/session_meta.py`): Session persistence and metadata

### Key Architectural Patterns
- **Tool Context Injection**: Tools can accept `ctx: ToolContext` parameter for emitting status/tool_stream events
- **Message Sequence Validation**: Agent loop auto-heals missing tool messages and sanitizes orphan tool messages
- **Workspace Sandbox**: All file operations restricted to `workspace_root` directory
- **Tool Budget Limits**: Prevents runaway tool calls with `max_tool_calls`, `max_tool_calls_per_tool`, `max_tool_calls_same_args`
- **Transport Protocol**: Runtime events encoded in versioned envelopes for WebSocket/HTTP transport (`ggbot/core/transport_protocol.py`)
- **Event-Driven Transcript**: JSONL event logging with strict ordering guarantees

## Configuration System

### Loading Priority
1. **Command-line arguments** (highest priority)
2. **Environment variables** (from shell or `.env` files)
3. **TOML configuration** (`.ggbot/config.toml`)
4. **Default values** (lowest priority)

### Essential Environment Variables
- `OPENAI_MODEL`: Model name for LiteLLM (e.g., `gpt-4.1-mini`, `Codex-3-5-sonnet-20241022`)
- `OPENAI_API_KEY`: API key for OpenAI-compatible providers
- `OPENAI_BASE_URL`: Base URL (default: `https://api.openai.com/v1`)
- `GGBOT_THINKING_ENABLED`: Enable thinking/reasoning output (default: `false`)
- `GGBOT_WORKSPACE_ROOT`: Workspace directory (default: current directory)
- `GGBOT_TRANSCRIPT_DIR`: Transcript directory (default: `.ggbot/transcripts`)
- `GGBOT_PROMPT_PROFILE`: Prompt profile name (default: `default`)
- `GGBOT_PROMPT_DIR`: Prompt directory (default: `./.ggbot/prompts`)

### Tool Budget Configuration
- `max_tool_calls`: Maximum tool calls per turn (default: 30)
- `max_tool_calls_per_tool`: Maximum calls per individual tool (default: 12)
- `max_tool_calls_same_args`: Maximum calls with identical arguments (default: 3)

### Example TOML Configuration
```toml
[openai]
api_key = "sk-xxxx"
base_url = "https://api.openai.com/v1"
model = "gpt-4.1-mini"

[ggbot]
max_turns = 8
max_tool_calls = 30
max_tool_calls_per_tool = 12
max_tool_calls_same_args = 3

[prompt]
profile = "default"
dir = "./.ggbot/prompts"

[shell]
confirm = true
timeout_ms = 30000
max_output_chars = 30000
```

## Thinking Functionality
When `GGBOT_THINKING_ENABLED=true`, GGbot extracts and displays model reasoning:
- Thinking messages use `role="thinking"` in internal types
- For API compatibility (e.g., DeepSeek), thinking messages are converted to `system` role with `[Thinking]` prefix
- Supported formats: `思考：...\n\n回答：...`, `Thinking: ...\n\nAnswer: ...`, `<thinking>...</thinking><answer>...</answer>`

## Tool System Architecture

### Tool Registration
Tools are registered using the `@tool` decorator from `ggbot.tools.registry`:
```python
from pydantic import BaseModel
from ggbot.tools.registry import tool

class MyArgs(BaseModel):
    param: str

@tool(name="my_tool", description="Does something", input_model=MyArgs)
def my_tool(args: MyArgs) -> str:
    return f"Result: {args.param}"
```

### Tool Context Injection
Tools can accept `ctx: ToolContext` for event emission:
```python
@tool(name="streaming_tool", description="Streaming tool", input_model=MyArgs)
def streaming_tool(ctx: ToolContext, args: MyArgs) -> str:
    ctx.emit("status", {"message": "Starting..."})
    ctx.emit("tool_stream", {"chunk": "Partial result"})
    return "Complete result"
```

### Built-in Tool Categories
- **File Operations**: `file_tools.py` (read, write, list, search files)
- **Shell Execution**: `shell_tool.py` (safe shell with confirmation), `shell_stream_tool.py` (streaming output)
- **HTTP Requests**: `http_tools.py` (GET, POST, web search, readability extraction)
- **Workspace Management**: `workspace_tools.py` (set workspace, list contents)
- **Job Management**: `jobs_tool.py` (background job control)
- **Status Updates**: `status_tool.py` (runtime status reporting)

### Adding New Tools
1. Create tool module in `ggbot/tools/` or add to existing module
2. Define Pydantic input model and tool function with `@tool` decorator
3. For streaming/status events, add `ctx: ToolContext` parameter
4. Register in `ggbot/cli.py` `_register_builtin_tools()`
5. Add tests in `tests/` following existing patterns

## Testing Patterns

### Test Fixtures & Mocks
- `tmp_path`: Isolated temporary directory for each test
- `monkeypatch`: Modify environment variables, module attributes, functions
- `httpx.MockTransport`: Mock HTTP requests with controlled responses
- Mock LiteLLM: `monkeypatch.setattr("litellm.completion", mock_completion)`

### Common Test Scenarios
1. **Tool Tests**: Verify tool functions with proper input/output
2. **Query Loop Tests**: Test agent loop with mocked provider responses
3. **Transcript Tests**: Verify event ordering and JSONL compatibility
4. **Configuration Tests**: Test config loading priority (env > .env > TOML > defaults)
5. **Integration Tests**: End-to-end scenarios with mocked dependencies

### Test Organization
- Tool-related: `uv run pytest -k "tool" -vv`
- Query loop: `uv run pytest -k "query_loop" -vv`
- Configuration: `uv run pytest -k "config" -vv`
- Async tools: `uv run pytest -k "async" -vv`
- Web tools: `uv run pytest -k "web" -vv`

## Runtime Events & Transcript System

### Event Types
- `model_message`: All chat messages (system/user/assistant/tool)
- `tool_call`: Tool invocation with parsed arguments
- `tool_result`: Tool execution result (length, error status, auto_healed flag)
- `tool_stream`: Incremental output from streaming tools (e.g., `shell_stream`)
- `status`: Runtime status updates from tools
- `provider_error`: Provider API failures

### Transport Protocol
Events are encoded in versioned envelopes (`ggbot/core/transport_protocol.py`):
- `version=1`: Protocol version for compatibility
- `seq`: Monotonically increasing sequence number per session
- `session_id`: Session identifier
- `ts_ms`: Timestamp in milliseconds
- `source`: Event source (e.g., `agent_runtime`, `query_loop`)
- `event_type`: Type matching transcript events
- `data`: Event payload

### Session Management
- Session types: `chat`, `repl`, `tui` (each has default transcript file)
- Resume sessions with `--resume` flag
- View transcripts: `ggbot log --follow --events`

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

### Common Debugging Scenarios
1. **API Connection Issues**: Verify `OPENAI_API_KEY` and `OPENAI_BASE_URL`
2. **Tool Execution Failures**: Check workspace permissions and tool budgets
3. **Transcript Issues**: Use `ggbot log --follow --events` to monitor runtime events
4. **Provider Compatibility**: Test with different `OPENAI_MODEL` values

### Configuration Testing
- Test config loading: `uv run pytest tests/test_config_load.py -v`
- Integration test: `uv run pytest tests/test_config_integration.py -v`
- Provider error handling: `uv run pytest tests/test_provider_error_handling.py -v`
- Transcript resume: `uv run pytest tests/test_transcript_resume.py -v`

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