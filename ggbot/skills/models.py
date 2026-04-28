from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SkillSpec:
    name: str
    description: str
    instructions: str
    trigger_keywords: list[str] = field(default_factory=list)
    preferred_tools: list[str] = field(default_factory=list)
    source_path: Path | None = None


@dataclass(frozen=True)
class SkillResolution:
    matched: bool
    skills: list[SkillSpec] = field(default_factory=list)
    scores: list[float] = field(default_factory=list)

