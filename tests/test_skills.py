from pathlib import Path

from ggbot.app.config import Settings
from ggbot.skills import SkillResolver, build_skill_system_message
from ggbot.skills import resolver as skill_resolver_module


def test_skill_resolver_match(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "skill-docx"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: skill-docx
description: DOCX processing
triggers: docx,word
tools: docx_create,docx_add_paragraph
---
Use docx tools for document tasks.
""",
        encoding="utf-8",
    )

    settings = Settings.load(workspace_root=tmp_path)
    settings.skills_enabled = True
    settings.skills_dir = skills_dir

    resolver = SkillResolver(settings=settings)
    resolution = resolver.resolve("请帮我创建一个docx并加标题")

    assert resolution.matched is True
    assert resolution.skills
    assert resolution.skills[0].name == "skill-docx"
    msg = build_skill_system_message(resolution)
    assert msg is not None
    assert "docx_create" in msg


def test_skill_resolver_prefers_workspace_ggbot_dir(tmp_path: Path) -> None:
    skills_dir = tmp_path / ".ggbot" / "skills"
    skill_dir = skills_dir / "skill-docx"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: skill-docx
description: DOCX via .ggbot
triggers: docx
tools: docx_create
---
Use .ggbot skills.
""",
        encoding="utf-8",
    )

    settings = Settings.load(workspace_root=tmp_path)
    settings.skills_enabled = True
    settings.skills_dir = None

    resolver = SkillResolver(settings=settings)
    resolution = resolver.resolve("create docx")
    assert resolution.matched is True
    assert resolution.skills
    assert resolution.skills[0].name == "skill-docx"


def test_skill_resolver_supports_workspace_root_skills_dir(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "skill-weather"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: skill-weather
description: Weather skill in workspace
triggers: weather,天气
tools: web_search
---
Use weather skill.
""",
        encoding="utf-8",
    )

    settings = Settings.load(workspace_root=tmp_path)
    settings.skills_enabled = True
    settings.skills_dir = None

    resolver = SkillResolver(settings=settings)
    resolution = resolver.resolve("帮我查天气")
    assert resolution.matched is True
    assert resolution.skills
    assert resolution.skills[0].name == "skill-weather"


def test_skill_resolver_includes_builtin_skill_dir(tmp_path: Path) -> None:
    settings = Settings.load(workspace_root=tmp_path)
    resolver = SkillResolver(settings=settings)
    built_in_dir = Path(skill_resolver_module.__file__).resolve().parent
    candidates = [path.resolve() for path in resolver._candidate_dirs()]  # noqa: SLF001
    assert built_in_dir in candidates
