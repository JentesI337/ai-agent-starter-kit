"""skills — Skill Management Domain.

Handles skill discovery, retrieval, validation, and injection into agent prompts.
  - SkillsService:       Main facade for skill operations
  - SkillDefinition:     Skill data model
  - SkillEligibility:    Skill eligibility data
  - SkillSnapshot:       Persists and restores skill state

Skills are loaded from: data/skills/ (see config)

Allowed imports FROM:
  shared, contracts, config, state, memory

NOT allowed:
  transport, agent (prevents circular), tools, workflows, services (deprecated)
"""

from app.skills.models import SkillDefinition, SkillEligibility, SkillSnapshot
from app.skills.service import SkillsService

__all__ = [
    "SkillDefinition",
    "SkillEligibility",
    "SkillSnapshot",
    "SkillsService",
]
