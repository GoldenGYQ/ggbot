from __future__ import annotations

from pathlib import Path

from .models import SkillSpec


def _parse_list(value: str) -> list[str]:
    raw = value.strip()
    if not raw:
        return []
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    items = [item.strip() for item in raw.split(",")]
    return [item for item in items if item]


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    content = text.lstrip()
    if not content.startswith("---\n"):
        return {}, text.strip()

    end_idx = content.find("\n---\n", 4)
    if end_idx == -1:
        return {}, text.strip()

    header = content[4:end_idx]
    body = content[end_idx + len("\n---\n") :].strip()
    meta: dict[str, str] = {}
    for raw_line in header.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip().lower()] = value.strip()
    return meta, body


def parse_skill_file(path: Path) -> SkillSpec:
    text = path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)
    name = meta.get("name") or path.parent.name
    description = meta.get("description", "").strip() or f"Skill loaded from {path.name}"
    keywords = _parse_list(meta.get("triggers", ""))
    tools = _parse_list(meta.get("tools", ""))
    return SkillSpec(
        name=name,
        description=description,
        instructions=body,
        trigger_keywords=keywords,
        preferred_tools=tools,
        source_path=path,
    )


def load_skills_from_dirs(skill_dirs: list[Path]) -> list[SkillSpec]:
    skills: list[SkillSpec] = []
    visited: set[Path] = set()

    for skill_dir in skill_dirs:
        if not skill_dir.exists() or not skill_dir.is_dir():
            continue
        for skill_file in sorted(skill_dir.glob("*/SKILL.md")):
            resolved = skill_file.resolve()
            if resolved in visited:
                continue
            visited.add(resolved)
            try:
                skills.append(parse_skill_file(resolved))
            except Exception:
                continue

    return skills

