from __future__ import annotations

from dataclasses import dataclass

from app.config import settings
from app.model_routing.capability_profile import ModelCapabilityProfile
from app.model_routing.model_registry import ModelRegistry


@dataclass(frozen=True)
class ModelRouteDecision:
    primary_model: str
    fallback_models: list[str]
    profile: ModelCapabilityProfile
    scores: dict[str, float]


class ModelRouter:
    def __init__(self, registry: ModelRegistry | None = None):
        self.registry = registry or ModelRegistry()

    def route(self, *, runtime: str, requested_model: str | None) -> ModelRouteDecision:
        requested = (requested_model or "").strip()
        runtime_key = (runtime or "").strip().lower()

        candidates: list[str] = []
        if requested:
            candidates.append(requested)

        if runtime_key == "local":
            candidates.extend([
                settings.local_model,
                settings.api_model,
            ])
        else:
            candidates.extend([
                settings.api_model,
                settings.local_model,
            ])

        deduped = self._dedupe(candidates)
        if not deduped:
            deduped = [settings.llm_model]

        scores = {candidate: self._score_candidate(candidate, runtime_key) for candidate in deduped}
        if requested:
            primary = requested
            fallbacks = [item for item in deduped if item != requested]
            fallbacks.sort(key=lambda item: scores.get(item, float("-inf")), reverse=True)
        else:
            ranked = sorted(deduped, key=lambda item: scores.get(item, float("-inf")), reverse=True)
            primary = ranked[0]
            fallbacks = ranked[1:]

        profile = self.registry.resolve(primary)
        return ModelRouteDecision(
            primary_model=primary,
            fallback_models=fallbacks,
            profile=profile,
            scores=scores,
        )

    def _dedupe(self, values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            item = (value or "").strip()
            if not item:
                continue
            if item in result:
                continue
            result.append(item)
        return result

    def _score_candidate(self, model_id: str, runtime_key: str) -> float:
        profile = self.registry.resolve(model_id)
        runtime_bonus = 0.0
        if runtime_key == "local" and model_id == settings.local_model:
            runtime_bonus = 6.0
        elif runtime_key == "api" and model_id == settings.api_model:
            runtime_bonus = 6.0

        return (
            profile.health_score * 100.0
            - (profile.expected_latency_ms / 100.0)
            - (profile.cost_score * 10.0)
            + runtime_bonus
        )
