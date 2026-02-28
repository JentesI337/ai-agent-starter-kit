from __future__ import annotations

from app.config import settings
from app.model_routing.capability_profile import ModelCapabilityProfile


class ModelRegistry:
    def __init__(self) -> None:
        self._profiles = self._build_default_profiles()
        self._default_profile = ModelCapabilityProfile(
            model_id="default",
            max_context=8000,
            reasoning_depth=2,
            reflection_passes=0,
            combine_steps=False,
            temperature=0.3,
            health_score=0.85,
            expected_latency_ms=1400,
            cost_score=0.5,
        )

    def resolve(self, model_id: str) -> ModelCapabilityProfile:
        candidate = (model_id or "").strip()
        if not candidate:
            return self._default_profile

        for profile in self._profiles:
            if profile.model_id == candidate:
                return profile

        for profile in self._profiles:
            if candidate.startswith(profile.model_id):
                return profile

        return self._default_profile

    def _build_default_profiles(self) -> list[ModelCapabilityProfile]:
        return [
            ModelCapabilityProfile(
                model_id=settings.local_model,
                max_context=8000,
                reasoning_depth=2,
                reflection_passes=0,
                combine_steps=False,
                temperature=0.2,
                health_score=0.92,
                expected_latency_ms=950,
                cost_score=0.15,
            ),
            ModelCapabilityProfile(
                model_id=settings.api_model,
                max_context=16000,
                reasoning_depth=3,
                reflection_passes=1,
                combine_steps=True,
                temperature=0.3,
                health_score=0.88,
                expected_latency_ms=700,
                cost_score=0.75,
            ),
        ]
