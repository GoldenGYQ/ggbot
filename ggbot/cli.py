"""Backward-compatible CLI module.

This shim keeps old entry points (`ggbot.cli`) working after the
implementation moved to `ggbot.command`.
"""

from .command import *  # noqa: F401,F403

