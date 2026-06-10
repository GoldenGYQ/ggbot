"""Tests for the 'ggbot init' CLI command."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ggbot.command import app


@pytest.mark.unit
def test_init_writes_workspace_env_file(tmp_path: Path) -> None:
    """'ggbot init --yes' should write a valid .env file with provided API key, base URL, and model."""
    runner = CliRunner()
    env = {
        "HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
    }
    result = runner.invoke(
        app,
        [
            "init",
            "--workspace-root",
            str(tmp_path),
            "--yes",
            "--api-key",
            "test-key",
            "--base-url",
            "https://example.com/v1",
            "--model",
            "demo-model",
            "--force",
        ],
        env=env,
    )

    assert result.exit_code == 0
    env_file = Path(tmp_path) / ".ggbot" / ".env"
    assert env_file.exists()
    content = env_file.read_text(encoding="utf-8")
    assert "# GGbot example environment" in content
    assert "OPENAI_API_KEY=test-key" in content
    assert "OPENAI_BASE_URL=https://example.com/v1" in content
    assert "OPENAI_MODEL=demo-model" in content


@pytest.mark.unit
def test_init_yes_without_api_key_keeps_placeholder(tmp_path: Path) -> None:
    """'ggbot init --yes' without --api-key should keep the placeholder comment."""
    runner = CliRunner()
    env = {
        "HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
    }
    result = runner.invoke(
        app,
        [
            "init",
            "--workspace-root",
            str(tmp_path),
            "--yes",
            "--force",
        ],
        env=env,
    )

    assert result.exit_code == 0
    env_file = Path(tmp_path) / ".ggbot" / ".env"
    content = env_file.read_text(encoding="utf-8")
    assert "# OPENAI_API_KEY=sk-your-key-here" in content

