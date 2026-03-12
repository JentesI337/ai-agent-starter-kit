from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _normalize_scope(value: str | None, *, fallback: str) -> str:
    candidate = (value or "").strip().lower()
    return candidate or fallback


def _normalize_agent_id(value: str | None) -> str:
    return (value or "").strip().lower() or "head-agent"


def _parse_pair(entry: str) -> tuple[str, str] | None:
    candidate = (entry or "").strip().lower()
    if not candidate:
        return None
    for separator in ("->", ">", ":"):
        if separator in candidate:
            source, target = candidate.split(separator, 1)
            left = source.strip()
            right = target.strip()
            if left and right:
                return left, right
            return None
    return None


@dataclass(frozen=True)
class AgentIsolationProfile:
    agent_id: str
    workspace_scope: str
    skills_scope: str
    credential_scope: str


@dataclass(frozen=True)
class AgentIsolationDecision:
    allowed: bool
    reason: str
    source_agent_id: str
    target_agent_id: str
    source_profile: AgentIsolationProfile
    target_profile: AgentIsolationProfile

    def as_details(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "source_agent_id": self.source_agent_id,
            "target_agent_id": self.target_agent_id,
            "source_scopes": {
                "workspace": self.source_profile.workspace_scope,
                "skills": self.source_profile.skills_scope,
                "credentials": self.source_profile.credential_scope,
            },
            "target_scopes": {
                "workspace": self.target_profile.workspace_scope,
                "skills": self.target_profile.skills_scope,
                "credentials": self.target_profile.credential_scope,
            },
        }


class AgentIsolationPolicy:
    def __init__(self, *, enabled: bool, allowed_cross_scope_pairs: set[tuple[str, str]]):
        self._enabled = bool(enabled)
        self._allowed_pairs = set(allowed_cross_scope_pairs)

    @classmethod
    def from_settings(cls, settings: Any) -> AgentIsolationPolicy:
        raw_pairs = list(getattr(settings, "agent_isolation_allowed_scope_pairs", []) or [])
        parsed_pairs: set[tuple[str, str]] = set()
        for entry in raw_pairs:
            parsed = _parse_pair(str(entry))
            if parsed is not None:
                parsed_pairs.add(parsed)
        return cls(
            enabled=bool(getattr(settings, "agent_isolation_enabled", True)),
            allowed_cross_scope_pairs=parsed_pairs,
        )

    def is_cross_scope_allowed(self, *, source_agent_id: str, target_agent_id: str) -> bool:
        source = _normalize_agent_id(source_agent_id)
        target = _normalize_agent_id(target_agent_id)
        return (source, target) in self._allowed_pairs or ("*", target) in self._allowed_pairs

    def evaluate(
        self,
        *,
        source_agent_id: str,
        target_agent_id: str,
        source_profile: AgentIsolationProfile,
        target_profile: AgentIsolationProfile,
    ) -> AgentIsolationDecision:
        normalized_source = _normalize_agent_id(source_agent_id)
        normalized_target = _normalize_agent_id(target_agent_id)

        if not self._enabled:
            return AgentIsolationDecision(
                allowed=True,
                reason="isolation_disabled",
                source_agent_id=normalized_source,
                target_agent_id=normalized_target,
                source_profile=source_profile,
                target_profile=target_profile,
            )

        scopes_match = (
            source_profile.workspace_scope == target_profile.workspace_scope
            and source_profile.skills_scope == target_profile.skills_scope
            and source_profile.credential_scope == target_profile.credential_scope
        )
        if scopes_match:
            return AgentIsolationDecision(
                allowed=True,
                reason="scope_match",
                source_agent_id=normalized_source,
                target_agent_id=normalized_target,
                source_profile=source_profile,
                target_profile=target_profile,
            )

        if self.is_cross_scope_allowed(source_agent_id=normalized_source, target_agent_id=normalized_target):
            return AgentIsolationDecision(
                allowed=True,
                reason="cross_scope_allowlisted",
                source_agent_id=normalized_source,
                target_agent_id=normalized_target,
                source_profile=source_profile,
                target_profile=target_profile,
            )

        return AgentIsolationDecision(
            allowed=False,
            reason="cross_scope_blocked",
            source_agent_id=normalized_source,
            target_agent_id=normalized_target,
            source_profile=source_profile,
            target_profile=target_profile,
        )


def resolve_agent_isolation_profile(*, agent_id: str, custom_definition: Any | None = None) -> AgentIsolationProfile:
    normalized_agent_id = _normalize_agent_id(agent_id)
    workspace_scope = _normalize_scope(
        getattr(custom_definition, "workspace_scope", None),
        fallback=normalized_agent_id,
    )
    skills_scope = _normalize_scope(
        getattr(custom_definition, "skills_scope", None),
        fallback=normalized_agent_id,
    )
    credential_scope = _normalize_scope(
        getattr(custom_definition, "credential_scope", None),
        fallback=normalized_agent_id,
    )
    return AgentIsolationProfile(
        agent_id=normalized_agent_id,
        workspace_scope=workspace_scope,
        skills_scope=skills_scope,
        credential_scope=credential_scope,
    )
