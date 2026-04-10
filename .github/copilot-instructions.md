# Project Guidelines

## Build and Test
- Create or use a Python 3.10+ environment.
- Install editable package with dev dependencies: `python -m pip install -e .[dev]`
- Run tests before finishing code changes: `pytest`
- Useful local runs:
  - `ggbot --help`
  - `ggbot chat "hello"`
  - `ggbot repl`
  - `ggbot tui`

See `README.md` for environment and configuration examples.

## Architecture
- CLI entrypoints live in `ggbot/cli.py` and expose `chat`, `repl`, and `tui` commands.
- Core orchestration is in `ggbot/core/query_loop.py` (streaming model loop and tool execution).
- Session/transcript persistence is in:
  - `ggbot/core/sessions.py`
  - `ggbot/core/session_meta.py`
  - `ggbot/core/transcript.py`
- Tooling is registry-based:
  - Tool decorator/registry in `ggbot/tools/registry.py`
  - Built-in tools in `ggbot/tools/`
- Provider client is in `ggbot/providers/openai_client.py`.

## Conventions
- Keep type hints and `from __future__ import annotations` style consistent with existing modules.
- New tools should use the `@tool(...)` decorator pattern and Pydantic input models.
- Preserve workspace sandbox guarantees for file/shell operations (see `ggbot/core/permissions.py`).
- Prefer focused tests under `tests/` for every behavior change; follow existing test style with `pytest`, `tmp_path`, and `httpx.MockTransport` where applicable.

## Critical Gotchas
- `OPENAI_API_KEY` must be configured or CLI operations that call the model will fail.
- Tool call message ordering matters in the query loop; avoid changing sequencing semantics unless corresponding tests are updated.
- Transcript storage is JSONL append-style events; preserve compatibility with resume logic.

## References
- Setup and runtime configuration: `README.md`
- Dependency/runtime/test config: `pyproject.toml`
- Main integration tests and behavioral examples: `tests/`