from __future__ import annotations

import os
import platform
import shutil

from app.skills.models import SkillDefinition

_OS_ALIASES = {
    "windows": {"windows", "win32", "win"},
    "linux": {"linux"},
    "darwin": {"darwin", "mac", "macos", "osx"},
}


def _normalize_os() -> str:
    return platform.system().strip().lower()


def _matches_os(allowed: tuple[str, ...], current_os: str) -> bool:
    if not allowed:
        return True
    normalized_allowed = {value.strip().lower() for value in allowed if value.strip()}
    for canonical, aliases in _OS_ALIASES.items():
        if current_os == canonical and normalized_allowed.intersection(aliases):
            return True
    return current_os in normalized_allowed


def is_skill_eligible(skill: SkillDefinition) -> tuple[bool, str | None]:
    current_os = _normalize_os()
    if not _matches_os(skill.metadata.os, current_os):
        return False, f"os_mismatch:{current_os}"

    for env_name in skill.metadata.requires_env:
        if not os.getenv(env_name):
            return False, f"missing_env:{env_name}"

    for bin_name in skill.metadata.requires_bins:
        if shutil.which(bin_name) is None:
            return False, f"missing_bin:{bin_name}"

    return True, None


def filter_eligible_skills(skills: list[SkillDefinition]) -> tuple[list[SkillDefinition], dict[str, str]]:
    eligible: list[SkillDefinition] = []
    rejected: dict[str, str] = {}

    for skill in skills:
        ok, reason = is_skill_eligible(skill)
        if ok:
            eligible.append(skill)
        else:
            rejected[skill.name] = reason or "ineligible"

    return eligible, rejected
