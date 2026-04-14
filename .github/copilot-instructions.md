# Project Guidelines

## Build and Test
- Use Python 3.10+.
- Prefer uv workflow:
  - `uv sync --extra dev`
  - `uv run pytest`
  - `uv run ggbot --help`
  - `uv run ggbot chat "hello"`
  - `uv run ggbot repl`
  - `uv run ggbot tui`
- Keep `pytest` green before finishing code changes.
- See `README.md` and `doc/tests.md` for full setup/test details.

## Architecture
- CLI entrypoints are in `ggbot/cli.py` (`chat`, `repl`, `tui`, `log`).
- TUI adapter is in `ggbot/ui/tui.py`.
- Query orchestration is in `ggbot/core/agent_loop.py`.
- Model/tool stages are split into:
  - `ggbot/core/model_interaction.py`
  - `ggbot/core/tool_execution.py`
  - `ggbot/core/history_repair.py`
- Runtime/session bootstrap and switching are in:
  - `ggbot/core/runtime.py`
  - `ggbot/core/session_store.py`
  - `ggbot/core/transcript.py`
- Provider client is LiteLLM-based in `ggbot/providers/litellm_client.py`.
- Runtime events and transport envelope are in:
  - `ggbot/core/events.py`
  - `ggbot/core/runtime_events.py`
  - `ggbot/core/transport_protocol.py`

## Conventions
- Keep type hints and `from __future__ import annotations` style consistent with existing modules.
- New tools should use the `@tool(...)` decorator pattern and Pydantic input models.
- Preserve workspace sandbox guarantees for file/shell operations (see `ggbot/core/permissions.py`).
- Keep adapter layers (CLI/TUI/future transport) thin: business logic belongs in core runtime modules.
- Prefer focused tests under `tests/` for each behavior change; follow existing style (`pytest`, `tmp_path`, `httpx.MockTransport` where applicable).

## Critical Gotchas
- `OPENAI_API_KEY` must be configured or CLI operations that call the model will fail.
- Tool call message ordering matters (`assistant tool_calls` must be followed by corresponding `tool` messages); avoid changing sequencing semantics unless tests are updated.
- Tool budgets are enforced in the agent loop (`max_tool_calls*`); repeated same-args tool calls can be auto-cancelled.
- Transcript storage is JSONL append-style events; preserve compatibility with resume/replay logic.
- If thinking is enabled, keep thinking extraction/event behavior consistent with existing tests.

## References
- Setup and runtime configuration: `README.md`
- Architecture and boundaries: `doc/architecture.md`
- Development guide: `doc/development.md`
- Configuration details: `doc/configuration.md`
- Tests reference: `doc/tests.md`
- Dependency/runtime/test config: `pyproject.toml`