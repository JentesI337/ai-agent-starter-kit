from __future__ import annotations

from app.skills.models import SkillDefinition


def _format_skill_entry(skill: SkillDefinition) -> str:
    description = skill.description.strip() or "(no description)"
    return (
        f"<available_skill>\n"
        f"  <name>{skill.name}</name>\n"
        f"  <description>{description}</description>\n"
        f"  <location>{skill.file_path}</location>\n"
        f"</available_skill>"
    )


def build_skills_prompt(skills: list[SkillDefinition], max_prompt_chars: int) -> tuple[str, int, bool]:
    if not skills:
        return "", 0, False

    chunks: list[str] = []
    selected = 0
    truncated = False

    for skill in skills:
        entry = _format_skill_entry(skill)
        candidate = "\n\n".join(chunks + [entry])
        if len(candidate) > max_prompt_chars:
            truncated = True
            break
        chunks.append(entry)
        selected += 1

    prompt = (
        "## Skills (preview)\n"
        "Prüfe zuerst die verfügbaren Skills. Wenn genau ein Skill klar passt, lies dessen SKILL.md.\n\n"
        f"{chr(10).join(chunks)}"
    )
    return prompt, selected, truncated
