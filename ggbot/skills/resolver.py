from __future__ import annotations

from pathlib import Path
import re

from ..app.config import Settings
from .loader import load_skills_from_dirs
from .models import SkillResolution, SkillSpec


def _normalize_text(text: str) -> str:
    lowered = (text or "").lower()
    return re.sub(r"\s+", " ", lowered).strip()


class SkillResolver:
    def __init__(self, *, settings: Settings) -> None:
        self._settings = settings

    def _candidate_dirs(self) -> list[Path]:
        dirs: list[Path] = []
        if self._settings.skills_dir is not None:
            dirs.append(self._settings.skills_dir)

        # Built-in skills shipped with the project codebase, e.g. ggbot/skills/weather/SKILL.md
        dirs.append(Path(__file__).resolve().parent)

        # Global skills in home directory.
        dirs.append(Path.home() / ".ggbot" / "skills")

        # Workspace-level skills under ~/.ggbot/workspace (or custom workspace_root).
        dirs.append(self._settings.workspace_root / "skills")

        # Backward compatibility for legacy locations.
        dirs.append(self._settings.workspace_root / ".ggbot" / "skills")
        dirs.append(self._settings.workspace_root / ".trae" / "skills")
        dirs.append(Path.cwd() / ".ggbot" / "skills")
        dirs.append(Path.cwd() / ".trae" / "skills")


        deduped: list[Path] = []
        seen: set[Path] = set()
        for directory in dirs:
            resolved = directory.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            deduped.append(directory)
        return deduped

    def _score_skill(self, text: str, skill: SkillSpec) -> float:
        score = 0.0
        if skill.name and skill.name.lower() in text:
            score += 3.0
        for keyword in skill.trigger_keywords:
            norm_kw = keyword.lower().strip()
            if norm_kw and norm_kw in text:
                score += 1.0
        if score == 0.0 and "docx" in text and "docx" in skill.name.lower():
            score = 1.0
        return score

    def resolve(self, user_text: str, *, max_skills: int = 2) -> SkillResolution:
        if not self._settings.skills_enabled:
            return SkillResolution(matched=False)

        skills = load_skills_from_dirs(self._candidate_dirs())
        if not skills:
            return SkillResolution(matched=False)

        text = _normalize_text(user_text)
        ranked: list[tuple[float, SkillSpec]] = []
        for skill in skills:
            score = self._score_skill(text, skill)
            if score > 0:
                ranked.append((score, skill))

        if not ranked:
            return SkillResolution(matched=False)

        ranked.sort(key=lambda item: item[0], reverse=True)
        top = ranked[: max(1, max_skills)]
        return SkillResolution(
            matched=True,
            skills=[item[1] for item in top],
            scores=[item[0] for item in top],
        )


def build_skill_system_message(resolution: SkillResolution) -> str | None:
    if not resolution.matched or not resolution.skills:
        return None

    lines = [
        "You must follow the activated skill guidance for this request.",
        "",
        "Activated skills:",
    ]
    for idx, skill in enumerate(resolution.skills, start=1):
        lines.append(f"{idx}. {skill.name}: {skill.description}")
        if skill.preferred_tools:
            lines.append(f"   Preferred tools: {', '.join(skill.preferred_tools)}")
        if skill.instructions:
            lines.append("   Instructions:")
            for skill_line in skill.instructions.splitlines():
                lines.append(f"   {skill_line}")
    return "\n".join(lines).strip()
