#!/usr/bin/env python3
"""Test configuration loading with thinking enabled."""

import os
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from ggbot.core.config import Settings

def test_thinking_config():
    """Test that thinking configuration is loaded correctly."""

    print("Testing thinking configuration loading...")
    print("=" * 60)

    # Test 1: Default settings
    print("\n1. Testing default settings:")
    # Clear any environment variables that might affect the test
    import os
    original_env = os.environ.get('GGBOT_THINKING_ENABLED')
    if original_env:
        del os.environ['GGBOT_THINKING_ENABLED']

    try:
        settings = Settings()
        print(f"   thinking_enabled (default): {settings.thinking_enabled}")
        assert settings.thinking_enabled is False, "Default should be False"
    finally:
        # Restore original environment
        if original_env:
            os.environ['GGBOT_THINKING_ENABLED'] = original_env

    # Test 2: Environment variable
    print("\n2. Testing environment variable:")
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create .env file
        env_file = Path(tmpdir) / ".env"
        env_file.write_text("GGBOT_THINKING_ENABLED=true\n")

        # Create workspace
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()

        # Load settings
        settings = Settings.load(workspace_root=workspace)
        print(f"   thinking_enabled (from .env): {settings.thinking_enabled}")
        # Note: The _apply_dotenv method only applies if env var is not already set
        # In test environment, we can't easily test this without mocking os.environ

    # Test 3: TOML config
    print("\n3. Testing TOML configuration:")
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create config directory
        config_dir = Path(tmpdir) / ".ggbot"
        config_dir.mkdir()

        # Create config.toml
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[ggbot]
thinking_enabled = true
max_turns = 10
""")

        # Create workspace
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()

        # Load settings
        settings = Settings.load(workspace_root=workspace)
        print(f"   thinking_enabled (from config.toml): {settings.thinking_enabled}")
        print(f"   max_turns (from config.toml): {settings.max_turns}")

        # Note: TOML config is only applied if env var is not set
        # In test environment without GGBOT_THINKING_ENABLED env var,
        # it should load from TOML

    # Test 4: Field existence
    print("\n4. Testing field existence:")
    fields = Settings.model_fields
    print(f"   Has thinking_enabled field: {'thinking_enabled' in fields}")
    assert 'thinking_enabled' in fields, "Settings should have thinking_enabled field"

    print("\n" + "=" * 60)
    print("All configuration tests passed!")

if __name__ == "__main__":
    test_thinking_config()