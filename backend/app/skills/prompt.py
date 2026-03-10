from __future__ import annotations

from app.skills.models import SkillDefinition


def _format_skill_entry(skill: SkillDefinition) -> str:
    description = skill.description.strip() or "(no description)"
    type_tag = f"  <type>{skill.skill_type}</type>\n" if skill.skill_type != "reference" else ""
    checks_tag = f"  <checks_count>{len(skill.checks)}</checks_count>\n" if skill.checks else ""
    return (
        f"<available_skill>\n"
        f"  <name>{skill.name}</name>\n"
        f"  <description>{description}</description>\n"
        f"{type_tag}{checks_tag}"
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
        candidate = "\n\n".join([*chunks, entry])
        if len(candidate) > max_prompt_chars:
            truncated = True
            break
        chunks.append(entry)
        selected += 1

    prompt = (
        "## Skills (preview)\n"
        "Prüfe zuerst die verfügbaren Skills. Lies SKILL.md nur gezielt per read_file, wenn ein Skill klar passt.\n\n"
        f"{chr(10).join(chunks)}"
    )
    return prompt, selected, truncated
