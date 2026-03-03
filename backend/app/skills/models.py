from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SkillMetadata:
    requires_bins: tuple[str, ...] = ()
    requires_env: tuple[str, ...] = ()
    os: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    description: str
    file_path: str
    base_dir: str
    body: str
    metadata: SkillMetadata = field(default_factory=SkillMetadata)
    user_invocable: bool = True
    disable_model_invocation: bool = False


@dataclass(frozen=True)
class SkillEligibility:
    skill_name: str
    eligible: bool
    reason: str | None = None


@dataclass(frozen=True)
class SkillPromptState:
    prompt: str
    discovered_count: int
    eligible_count: int
    selected_count: int
    truncated: bool


@dataclass(frozen=True)
class SkillSnapshot:
    prompt: str
    skills: tuple[dict[str, str | list[str] | None], ...]
    discovered_count: int
    eligible_count: int
    selected_count: int
    truncated: bool
