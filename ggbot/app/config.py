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


def _default_workspace_root() -> Path:
    return (Path.home() / ".ggbot" / "workspace").resolve()


def _default_transcript_dir() -> Path:
    return (Path.home() / ".ggbot" / "transcripts").resolve()


def _default_config_home() -> Path:
    return (Path.home() / ".ggbot").resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="",
        extra="ignore",
        populate_by_name=True,
    )

    # Model
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")

    # Workspace / sandbox
    workspace_root: Path = Field(default_factory=_default_workspace_root, alias="GGBOT_WORKSPACE_ROOT")

    # Behavior
    max_turns: int = Field(default=8, alias="GGBOT_MAX_TURNS")

    # Tool loop safety (prevents runaway repeated tool calls)
    max_tool_calls: int = Field(default=30, alias="GGBOT_MAX_TOOL_CALLS")
    max_tool_calls_per_tool: int = Field(default=20, alias="GGBOT_MAX_TOOL_CALLS_PER_TOOL")
    max_tool_calls_same_args: int = Field(default=3, alias="GGBOT_MAX_TOOL_CALLS_SAME_ARGS")

    # Transcript
    transcript_dir: Path | None = Field(default=None, alias="GGBOT_TRANSCRIPT_DIR")

    # Prompt engineering
    prompt_profile: str = Field(default="default", alias="GGBOT_PROMPT_PROFILE")
    prompt_dir: Path | None = Field(default=None, alias="GGBOT_PROMPT_DIR")

    # Shell safety
    shell_confirm: bool = Field(default=True, alias="GGBOT_SHELL_CONFIRM")
    shell_timeout_ms: int = Field(default=30_000, alias="GGBOT_SHELL_TIMEOUT_MS")
    shell_max_output_chars: int = Field(default=30_000, alias="GGBOT_SHELL_MAX_OUTPUT_CHARS")

    # Thinking/Reasoning functionality
    thinking_enabled: bool = Field(default=False, alias="GGBOT_THINKING_ENABLED")

    # Skills
    skills_enabled: bool = Field(default=True, alias="GGBOT_SKILLS_ENABLED")
    skills_dir: Path | None = Field(default=None, alias="GGBOT_SKILLS_DIR")

    def resolved_transcript_dir(self) -> Path:
        if self.transcript_dir is not None:
            return self.transcript_dir
        return _default_transcript_dir()

    @classmethod
    def load(cls, *, workspace_root: Path | None = None) -> "Settings":
        """Load settings from (in priority order):

        1) real environment variables
        2) global dotenv file: ~/.ggbot/.env
        3) global TOML config: ~/.ggbot/config.toml (only fills values not set by env)
        4) defaults

        This matches the expectation: you can put API keys in .env/config.toml,
        but exported env vars always win.
        """

        root = workspace_root or _default_workspace_root()

        # Load from real environment variables only. We intentionally do NOT rely on
        # BaseSettings env_file handling because its paths are resolved relative to
        # the process CWD, which can cause ambient repo-level .env leakage when
        # workspace_root is explicitly provided (e.g., tests).
        settings = cls()
        settings.workspace_root = root

        # Global TOML config (optional)
        config_path = (_default_config_home() / "config.toml").resolve()
        if tomllib is not None and config_path.exists():
            try:
                data = tomllib.loads(config_path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
            cls._apply_toml_config(settings, data)

        # Dotenv (optional): only fills values not set by real env vars.
        # Precedence: env > dotenv > toml > defaults.
        cls._apply_dotenv(settings)

        return settings

    @classmethod
    def _apply_dotenv(cls, settings: "Settings") -> None:
        values: dict[str, str] = {}
        config_home = _default_config_home()

        # Global dotenv only.
        values.update(_read_dotenv_file(config_home / ".env"))

        def apply(env_name: str, attr: str, *, kind: str) -> None:
            if env_name not in values:
                return
            if env_name in os.environ:
                return
            raw = values[env_name]
            coerced = _coerce_env_value(raw, kind=kind, root=config_home)
            setattr(settings, attr, coerced)

        apply("OPENAI_BASE_URL", "openai_base_url", kind="str")
        apply("OPENAI_API_KEY", "openai_api_key", kind="str_or_none")
        apply("OPENAI_MODEL", "openai_model", kind="str")

        apply("GGBOT_WORKSPACE_ROOT", "workspace_root", kind="path")

        apply("GGBOT_MAX_TURNS", "max_turns", kind="int")

        apply("GGBOT_MAX_TOOL_CALLS", "max_tool_calls", kind="int")
        apply("GGBOT_MAX_TOOL_CALLS_PER_TOOL", "max_tool_calls_per_tool", kind="int")
        apply("GGBOT_MAX_TOOL_CALLS_SAME_ARGS", "max_tool_calls_same_args", kind="int")

        apply("GGBOT_TRANSCRIPT_DIR", "transcript_dir", kind="path_or_none")

        apply("GGBOT_PROMPT_PROFILE", "prompt_profile", kind="str")
        apply("GGBOT_PROMPT_DIR", "prompt_dir", kind="path_or_none")

        apply("GGBOT_SHELL_CONFIRM", "shell_confirm", kind="bool")
        apply("GGBOT_SHELL_TIMEOUT_MS", "shell_timeout_ms", kind="int")
        apply("GGBOT_SHELL_MAX_OUTPUT_CHARS", "shell_max_output_chars", kind="int")

        apply("GGBOT_THINKING_ENABLED", "thinking_enabled", kind="bool")
        apply("GGBOT_SKILLS_ENABLED", "skills_enabled", kind="bool")
        apply("GGBOT_SKILLS_DIR", "skills_dir", kind="path_or_none")

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
        prompt = (data.get("prompt") or {}) if isinstance(data.get("prompt"), dict) else {}

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

        cls._apply_if_env_missing(settings, "GGBOT_PROMPT_PROFILE", "prompt_profile", prompt.get("profile"))

        pd = prompt.get("dir")
        if pd is not None and "GGBOT_PROMPT_DIR" not in os.environ:
            settings.prompt_dir = Path(str(pd))

        cls._apply_if_env_missing(settings, "GGBOT_SHELL_CONFIRM", "shell_confirm", shell.get("confirm"))
        cls._apply_if_env_missing(settings, "GGBOT_SHELL_TIMEOUT_MS", "shell_timeout_ms", shell.get("timeout_ms"))
        cls._apply_if_env_missing(
            settings,
            "GGBOT_SHELL_MAX_OUTPUT_CHARS",
            "shell_max_output_chars",
            shell.get("max_output_chars"),
        )

        cls._apply_if_env_missing(settings, "GGBOT_THINKING_ENABLED", "thinking_enabled", ggbot.get("thinking_enabled"))
        cls._apply_if_env_missing(settings, "GGBOT_SKILLS_ENABLED", "skills_enabled", ggbot.get("skills_enabled"))

        skills_dir = ggbot.get("skills_dir")
        if skills_dir is not None and "GGBOT_SKILLS_DIR" not in os.environ:
            settings.skills_dir = Path(str(skills_dir))


def _read_dotenv_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k:
            continue
        # Remove simple surrounding quotes.
        if len(v) >= 2 and v[0] == v[-1] and v[0] in {"\"", "'"}:
            v = v[1:-1]
        out[k] = v

    return out


_MIN_CONFIG_INT = -(2**63)
_MAX_CONFIG_INT = 2**63 - 1


def _parse_config_int(raw: str) -> int:
    value = raw.strip()
    if not value:
        raise ValueError("Invalid integer value: empty string")

    if value[0] in {"+", "-"}:
        digits = value[1:]
    else:
        digits = value

    if not digits or not digits.isdigit():
        raise ValueError(f"Invalid integer value: {raw!r}")

    parsed = int(value)
    if parsed < _MIN_CONFIG_INT or parsed > _MAX_CONFIG_INT:
        raise ValueError(
            f"Integer value out of allowed range [{_MIN_CONFIG_INT}, {_MAX_CONFIG_INT}]: {raw!r}"
        )
    return parsed


def _coerce_env_value(raw: str, *, kind: str, root: Path) -> Any:
    if kind == "str":
        return raw
    if kind == "str_or_none":
        return raw if raw != "" else None
    if kind == "int":
        return _parse_config_int(raw)
    if kind == "bool":
        v = raw.strip().lower()
        if v in {"1", "true", "yes", "y", "on"}:
            return True
        if v in {"0", "false", "no", "n", "off"}:
            return False
        raise ValueError(f"Invalid boolean value: {raw!r}")
    if kind == "path":
        p = Path(raw)
        return p if p.is_absolute() else (root / p)
    if kind == "path_or_none":
        if raw == "":
            return None
        p = Path(raw)
        return p if p.is_absolute() else (root / p)
    raise ValueError(f"Unknown coercion kind: {kind}")
