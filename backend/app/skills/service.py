from __future__ import annotations

from dataclasses import dataclass

from app.skills.discovery import discover_skills
from app.skills.eligibility import filter_eligible_skills
from app.skills.models import SkillSnapshot
from app.skills.snapshot import build_skill_snapshot


@dataclass(frozen=True)
class SkillsRuntimeConfig:
    enabled: bool
    skills_dir: str
    max_discovered: int
    max_prompt_chars: int


class SkillsService:
    def __init__(self, config: SkillsRuntimeConfig):
        self._config = config

    def build_snapshot(self) -> SkillSnapshot:
        if not self._config.enabled:
            return SkillSnapshot(
                prompt="",
                skills=(),
                discovered_count=0,
                eligible_count=0,
                selected_count=0,
                truncated=False,
            )

        discovered = discover_skills(
            skills_root=self._config.skills_dir,
            max_discovered=self._config.max_discovered,
        )
        eligible, _ = filter_eligible_skills(discovered)
        return build_skill_snapshot(
            discovered=discovered,
            eligible=eligible,
            max_prompt_chars=self._config.max_prompt_chars,
        )
