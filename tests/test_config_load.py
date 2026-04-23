import os
from pathlib import Path

import pytest

from ggbot.app.config import Settings


def test_load_reads_toml_when_env_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    # Also delete GGbot-specific env vars that might be set by .env file or other tests
    monkeypatch.delenv("GGBOT_MAX_TURNS", raising=False)
    monkeypatch.delenv("GGBOT_THINKING_ENABLED", raising=False)
    monkeypatch.delenv("GGBOT_PROMPT_PROFILE", raising=False)

    config_home = tmp_path / ".ggbot_home"
    config_home.mkdir()
    monkeypatch.setattr("ggbot.app.config._default_config_home", lambda: config_home)

    (config_home / "config.toml").write_text(
        """
[openai]
api_key = "from_toml"
model = "m1"

[ggbot]
max_turns = 3

[prompt]
profile = "strict"
dir = "custom-prompts"
""".strip(),
        encoding="utf-8",
    )

    s = Settings.load(workspace_root=tmp_path)
    assert s.openai_api_key == "from_toml"
    assert s.openai_model == "m1"
    assert s.max_turns == 3
    assert s.prompt_profile == "strict"
    assert s.prompt_dir == Path("custom-prompts")


def test_env_overrides_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "from_env")
    config_home = tmp_path / ".ggbot_home"
    config_home.mkdir()
    monkeypatch.setattr("ggbot.app.config._default_config_home", lambda: config_home)

    (config_home / "config.toml").write_text(
        """
[openai]
api_key = "from_toml"
""".strip(),
        encoding="utf-8",
    )

    s = Settings.load(workspace_root=tmp_path)
    assert s.openai_api_key == "from_env"


def test_load_uses_home_based_workspace_root_by_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GGBOT_WORKSPACE_ROOT", raising=False)
    monkeypatch.setattr("ggbot.app.config._default_workspace_root", lambda: tmp_path / "home_ws")

    s = Settings.load()

    assert s.workspace_root == (tmp_path / "home_ws")


def test_load_uses_home_based_transcript_dir_by_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GGBOT_TRANSCRIPT_DIR", raising=False)
    monkeypatch.setattr("ggbot.app.config._default_workspace_root", lambda: tmp_path / "home_ws")
    monkeypatch.setattr("ggbot.app.config._default_transcript_dir", lambda: tmp_path / "home_transcripts")

    s = Settings.load()

    assert s.resolved_transcript_dir() == (tmp_path / "home_transcripts")
