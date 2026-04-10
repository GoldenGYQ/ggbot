from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    import tomllib  # py3.11+
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="",
        extra="ignore",
        populate_by_name=True,
        env_file=(".env", ".ggbot/.env"),
        env_file_encoding="utf-8",
    )

    # Model
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")

    # Workspace / sandbox
    workspace_root: Path = Field(default_factory=lambda: Path.cwd(), alias="GGBOT_WORKSPACE_ROOT")

    # Behavior
    max_turns: int = Field(default=8, alias="GGBOT_MAX_TURNS")

    # Tool loop safety (prevents runaway repeated tool calls)
    max_tool_calls: int = Field(default=30, alias="GGBOT_MAX_TOOL_CALLS")
    max_tool_calls_per_tool: int = Field(default=12, alias="GGBOT_MAX_TOOL_CALLS_PER_TOOL")
    max_tool_calls_same_args: int = Field(default=3, alias="GGBOT_MAX_TOOL_CALLS_SAME_ARGS")

    # Transcript
    transcript_dir: Path | None = Field(default=None, alias="GGBOT_TRANSCRIPT_DIR")

    # Shell safety
    shell_confirm: bool = Field(default=True, alias="GGBOT_SHELL_CONFIRM")
    shell_timeout_ms: int = Field(default=30_000, alias="GGBOT_SHELL_TIMEOUT_MS")
    shell_max_output_chars: int = Field(default=30_000, alias="GGBOT_SHELL_MAX_OUTPUT_CHARS")

    def resolved_transcript_dir(self) -> Path:
        if self.transcript_dir is not None:
            return self.transcript_dir
        return (self.workspace_root / ".ggbot" / "transcripts").resolve()

    @classmethod
    def load(cls, *, workspace_root: Path | None = None) -> "Settings":
        """Load settings from (in priority order):

        1) real environment variables
        2) dotenv files: ./.env, ./.ggbot/.env
        3) TOML config: ./.ggbot/config.toml (only fills values not set by env)
        4) defaults

        This matches the expectation: you can put API keys in .env/config.toml,
        but exported env vars always win.
        """

        settings = cls()
        if workspace_root is not None:
            settings.workspace_root = workspace_root

        # TOML config (optional)
        config_path = (settings.workspace_root / ".ggbot" / "config.toml").resolve()
        if tomllib is not None and config_path.exists():
            try:
                data = tomllib.loads(config_path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
            cls._apply_toml_config(settings, data)

        return settings

    @staticmethod
    def _apply_if_env_missing(settings: "Settings", env_name: str, attr: str, value: Any) -> None:
        if value is None:
            return
        if env_name in os.environ:
            return
        setattr(settings, attr, value)

    @classmethod
    def _apply_toml_config(cls, settings: "Settings", data: dict[str, Any]) -> None:
        openai = (data.get("openai") or {}) if isinstance(data.get("openai"), dict) else {}
        ggbot = (data.get("ggbot") or {}) if isinstance(data.get("ggbot"), dict) else {}
        shell = (data.get("shell") or {}) if isinstance(data.get("shell"), dict) else {}
        transcript = (data.get("transcript") or {}) if isinstance(data.get("transcript"), dict) else {}

        cls._apply_if_env_missing(settings, "OPENAI_BASE_URL", "openai_base_url", openai.get("base_url"))
        cls._apply_if_env_missing(settings, "OPENAI_API_KEY", "openai_api_key", openai.get("api_key"))
        cls._apply_if_env_missing(settings, "OPENAI_MODEL", "openai_model", openai.get("model"))

        ws = ggbot.get("workspace_root")
        if ws is not None and "GGBOT_WORKSPACE_ROOT" not in os.environ:
            settings.workspace_root = Path(str(ws))

        cls._apply_if_env_missing(settings, "GGBOT_MAX_TURNS", "max_turns", ggbot.get("max_turns"))

        cls._apply_if_env_missing(settings, "GGBOT_MAX_TOOL_CALLS", "max_tool_calls", ggbot.get("max_tool_calls"))
        cls._apply_if_env_missing(
            settings,
            "GGBOT_MAX_TOOL_CALLS_PER_TOOL",
            "max_tool_calls_per_tool",
            ggbot.get("max_tool_calls_per_tool"),
        )
        cls._apply_if_env_missing(
            settings,
            "GGBOT_MAX_TOOL_CALLS_SAME_ARGS",
            "max_tool_calls_same_args",
            ggbot.get("max_tool_calls_same_args"),
        )

        td = transcript.get("dir")
        if td is not None and "GGBOT_TRANSCRIPT_DIR" not in os.environ:
            settings.transcript_dir = Path(str(td))

        cls._apply_if_env_missing(settings, "GGBOT_SHELL_CONFIRM", "shell_confirm", shell.get("confirm"))
        cls._apply_if_env_missing(settings, "GGBOT_SHELL_TIMEOUT_MS", "shell_timeout_ms", shell.get("timeout_ms"))
        cls._apply_if_env_missing(
            settings,
            "GGBOT_SHELL_MAX_OUTPUT_CHARS",
            "shell_max_output_chars",
            shell.get("max_output_chars"),
        )
