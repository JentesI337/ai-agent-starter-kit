from __future__ import annotations

from app.skills.models import SkillDefinition, SkillSnapshot
from app.skills.prompt import build_skills_prompt


def build_skill_snapshot(
    discovered: list[SkillDefinition],
    eligible: list[SkillDefinition],
    max_prompt_chars: int,
) -> SkillSnapshot:
    prompt, selected_count, truncated = build_skills_prompt(eligible, max_prompt_chars=max_prompt_chars)
    skills = tuple(
        {
            "name": skill.name,
            "description": skill.description,
            "file_path": skill.file_path,
            "requires_env": list(skill.metadata.requires_env),
            "requires_bins": list(skill.metadata.requires_bins),
            "os": list(skill.metadata.os),
        }
        for skill in eligible[:selected_count]
    )
    return SkillSnapshot(
        prompt=prompt,
        skills=skills,
        discovered_count=len(discovered),
        eligible_count=len(eligible),
        selected_count=selected_count,
        truncated=truncated,
    )
