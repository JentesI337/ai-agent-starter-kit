from __future__ import annotations

import contextlib
from pathlib import Path

from app.skills.models import SkillDefinition
from app.skills.parser import parse_skill_markdown

SKILL_FILE_NAME = "SKILL.md"


def discover_skills(skills_root: str, max_discovered: int) -> list[SkillDefinition]:
    root = Path(skills_root).resolve()
    if not root.exists() or not root.is_dir():
        return []

    results: list[SkillDefinition] = []

    root_skill = root / SKILL_FILE_NAME
    if root_skill.exists() and root_skill.is_file():
        with contextlib.suppress(Exception):  # M-25: skip broken root skill, continue with child discovery
            results.append(parse_skill_markdown(root_skill))

    for child in sorted(root.iterdir()):
        if len(results) >= max_discovered:
            break
        if not child.is_dir() or child.name.startswith("."):
            continue
        skill_file = child / SKILL_FILE_NAME
        if not skill_file.exists() or not skill_file.is_file():
            continue
        try:
            results.append(parse_skill_markdown(skill_file))
        except Exception:
            continue

    return results
