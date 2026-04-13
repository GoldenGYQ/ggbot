import os
from pathlib import Path

import pytest

from ggbot.core.config import Settings


def test_load_reads_toml_when_env_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    (tmp_path / ".ggbot").mkdir()
    (tmp_path / ".ggbot" / "config.toml").write_text(
        """
[openai]
api_key = "from_toml"
model = "m1"

[ggbot]
max_turns = 3
""".strip(),
        encoding="utf-8",
    )

    s = Settings.load(workspace_root=tmp_path)
    assert s.openai_api_key == "from_toml"
    assert s.openai_model == "m1"
    assert s.max_turns == 3


def test_env_overrides_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "from_env")

    (tmp_path / ".ggbot").mkdir()
    (tmp_path / ".ggbot" / "config.toml").write_text(
        """
[openai]
api_key = "from_toml"
""".strip(),
        encoding="utf-8",
    )

    s = Settings.load(workspace_root=tmp_path)
    assert s.openai_api_key == "from_env"
