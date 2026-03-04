from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.config import settings
from app.model_routing.capability_profile import ModelCapabilityProfile
from app.model_routing.model_registry import ModelRegistry

if TYPE_CHECKING:
    from app.services.model_health_tracker import ModelHealthTracker


@dataclass(frozen=True)
class ModelRouteDecision:
    primary_model: str
    fallback_models: list[str]
    profile: ModelCapabilityProfile
    scores: dict[str, float]


class ModelRouter:
    def __init__(
        self,
        registry: ModelRegistry | None = None,
        health_tracker: ModelHealthTracker | None = None,
    ):
        self.registry = registry or ModelRegistry()
        self._health_tracker = health_tracker

    def route(
        self,
        *,
        runtime: str,
        requested_model: str | None,
        reasoning_level: str | None = None,
    ) -> ModelRouteDecision:
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

        scores = {
            candidate: self._score_candidate(candidate, runtime_key, reasoning_level=reasoning_level)
            for candidate in deduped
        }
        if requested:
            primary = requested
            fallbacks = [item for item in deduped if item != requested]
            fallbacks.sort(key=lambda item: scores.get(item, float("-inf")), reverse=True)
        else:
            ranked = sorted(deduped, key=lambda item: scores.get(item, float("-inf")), reverse=True)
            primary = ranked[0]
            fallbacks = ranked[1:]

        profile = self.registry.resolve(primary)
        # T2.1: Gemessene Profile überschreiben statische wenn genug Samples vorhanden
        if self._health_tracker is not None:
            profile = self._health_tracker.apply_to_profile(profile)
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

    @staticmethod
    def _normalize_reasoning_level(reasoning_level: str | None) -> str:
        normalized = str(reasoning_level or "").strip().lower()
        if normalized in {"low", "medium", "high", "ultrathink", "adaptive"}:
            return normalized
        return "medium"

    def _score_candidate(self, model_id: str, runtime_key: str, *, reasoning_level: str | None = None) -> float:
        profile = self.registry.resolve(model_id)
        # T2.1: Use measured profile if available
        if self._health_tracker is not None:
            profile = self._health_tracker.apply_to_profile(profile)
        runtime_bonus = 0.0
        if runtime_key == "local" and model_id == settings.local_model:
            runtime_bonus = settings.model_score_runtime_bonus
        elif runtime_key == "api" and model_id == settings.api_model:
            runtime_bonus = settings.model_score_runtime_bonus

        normalized_reasoning_level = self._normalize_reasoning_level(reasoning_level)
        reasoning_bonus = 0.0
        if normalized_reasoning_level in {"high", "ultrathink"}:
            reasoning_bonus += float(profile.reasoning_depth) * 10.0
            reasoning_bonus += float(profile.max_context) / 8000.0
        elif normalized_reasoning_level == "low":
            reasoning_bonus -= float(profile.reasoning_depth) * 5.0
            reasoning_bonus -= float(profile.cost_score) * 6.0
            reasoning_bonus += max(0.0, 2000.0 - float(profile.expected_latency_ms)) / 400.0
        elif normalized_reasoning_level == "adaptive":
            reasoning_bonus += float(profile.reasoning_depth) * 3.0
            reasoning_bonus -= float(profile.cost_score) * 2.0

        return (
            profile.health_score * settings.model_score_weight_health
            - (profile.expected_latency_ms * settings.model_score_weight_latency)
            - (profile.cost_score * settings.model_score_weight_cost)
            + runtime_bonus
            + reasoning_bonus
        )
