"""
Capability Router — selects a model based on task requirements, never by
hardcoded model name.

Routes tasks using:
  - task_complexity: simple / moderate / complex
  - context_size: token count of required input
  - confidence_score: output from previous agent pass
  - budget_threshold: cost ceiling per task

Tier mapping:
  Small  (7B–14B)  → Basic coding, simple planning, minor fixes
  Mid    (32B–70B) → Combined steps, one reflection pass, dependency graphs
  High   (70B+/GPT-4) → Architecture design, security audits, deep refactors
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.orchestrator.contracts.schemas import (
    ModelCapabilityProfile,
    ModelTier,
    RoutingRequest,
    RoutingResult,
    TaskComplexity,
)

logger = logging.getLogger(__name__)

# Tier ordering for escalation / comparison
_TIER_ORDER: dict[ModelTier, int] = {
    ModelTier.SMALL: 0,
    ModelTier.MID: 1,
    ModelTier.HIGH: 2,
}

_TIER_FROM_STR: dict[str, ModelTier] = {
    "small": ModelTier.SMALL,
    "mid": ModelTier.MID,
    "high": ModelTier.HIGH,
}


class CapabilityRouter:
    """
    Model-agnostic capability router.

    Loads model profiles and routing rules from JSON config files.
    Selects models by task requirements — never by hardcoded name.
    """

    def __init__(
        self,
        models_config_path: str | None = None,
        routing_rules_path: str | None = None,
    ):
        config_dir = Path(__file__).resolve().parent.parent.parent.parent / "config"
        self._models_path = Path(models_config_path) if models_config_path else config_dir / "models.json"
        self._rules_path = Path(routing_rules_path) if routing_rules_path else config_dir / "routing_rules.json"

        self._profiles: list[ModelCapabilityProfile] = []
        self._profiles_by_tier: dict[ModelTier, list[ModelCapabilityProfile]] = {}
        self._rules: dict[str, Any] = {}

        self._load_profiles()
        self._load_rules()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(self, request: RoutingRequest) -> RoutingResult:
        """
        Select the best model for a task based on requirements.
        Never selects by hardcoded model name.
        """
        target_tier = self._determine_tier(request)

        # Apply budget constraint at selection time: try target tier first,
        # then fall back to cheaper tiers if nothing is affordable.
        if request.budget_threshold < float("inf"):
            selected = self._select_within_budget(target_tier, request)
        else:
            selected = self._select_from_tier(target_tier, request)

        if selected is None:
            # Escalate if no model found in target tier
            selected = self._escalate(target_tier, request)

        if selected is None:
            # Last resort: pick the widest-context profile available
            selected = self._fallback_any(request)

        if selected is None:
            raise RuntimeError("No model profiles registered — cannot route task")

        fallback = self._find_fallback(selected, request)

        reason = (
            f"tier={target_tier.value} complexity={request.task_complexity.value} "
            f"ctx={request.context_size} confidence={request.confidence_score:.2f}"
        )
        logger.info(
            "capability_router routed model=%s tier=%s reason=%s",
            selected.model_id,
            selected.tier.value,
            reason,
        )
        return RoutingResult(
            selected_model=selected,
            reason=reason,
            fallback_model=fallback,
        )

    def register_profile(self, profile: ModelCapabilityProfile) -> None:
        """Dynamically register a model profile at runtime."""
        self._profiles.append(profile)
        self._profiles_by_tier.setdefault(profile.tier, []).append(profile)
        logger.info("capability_router registered model=%s tier=%s", profile.model_id, profile.tier.value)

    def get_profiles(self) -> list[ModelCapabilityProfile]:
        return list(self._profiles)

    def get_profiles_by_tier(self, tier: ModelTier) -> list[ModelCapabilityProfile]:
        return list(self._profiles_by_tier.get(tier, []))

    # ------------------------------------------------------------------
    # Tier determination
    # ------------------------------------------------------------------

    def _determine_tier(self, request: RoutingRequest) -> ModelTier:
        """
        Apply routing rules to determine the target tier.
        Rules are evaluated in order; first matching rule wins.
        Escalation and min-tier rules are applied afterwards.
        """
        base_tier = self._complexity_to_tier(request.task_complexity)

        rules = self._rules.get("rules", [])
        for rule in rules:
            conditions = rule.get("conditions", {})
            if not self._conditions_match(conditions, request):
                continue

            # Direct tier assignment
            if "target_tier" in rule:
                tier_str = rule["target_tier"]
                base_tier = _TIER_FROM_STR.get(tier_str, base_tier)
                logger.debug("routing_rule matched rule=%s tier=%s", rule.get("name"), tier_str)

            # Tier escalation
            if "escalate_tiers" in rule:
                steps = int(rule["escalate_tiers"])
                current_order = _TIER_ORDER.get(base_tier, 0)
                new_order = min(current_order + steps, 2)
                for tier, order in _TIER_ORDER.items():
                    if order == new_order:
                        base_tier = tier
                        break
                logger.debug("routing_rule escalated rule=%s to=%s", rule.get("name"), base_tier.value)

            # Minimum tier floor
            if "min_tier" in rule:
                min_tier = _TIER_FROM_STR.get(rule["min_tier"], ModelTier.SMALL)
                if _TIER_ORDER.get(base_tier, 0) < _TIER_ORDER.get(min_tier, 0):
                    base_tier = min_tier

        # Budget enforcement: if budget is tight, try to use cheaper tier
        budget_conf = self._rules.get("budget_enforcement", {})
        if budget_conf.get("enabled") and budget_conf.get("fallback_to_cheaper"):
            if request.budget_threshold < float("inf"):
                base_tier = self._apply_budget_constraint(base_tier, request.budget_threshold)

        return base_tier

    def _conditions_match(self, conditions: dict[str, Any], request: RoutingRequest) -> bool:
        """Check if all conditions in a routing rule match the request."""
        # task_complexity
        if "task_complexity" in conditions:
            allowed = conditions["task_complexity"]
            if request.task_complexity.value not in allowed:
                return False

        # context_size range
        if "min_context_size" in conditions:
            if request.context_size < conditions["min_context_size"]:
                return False
        if "max_context_size" in conditions:
            if request.context_size > conditions["max_context_size"]:
                return False

        # confidence_score range
        if "min_confidence_score" in conditions:
            if request.confidence_score < conditions["min_confidence_score"]:
                return False
        if "max_confidence_score" in conditions:
            if request.confidence_score > conditions["max_confidence_score"]:
                return False

        # reflection requirement
        if "required_reflection" in conditions:
            if request.required_reflection != conditions["required_reflection"]:
                return False

        return True

    def _select_within_budget(
        self, start_tier: ModelTier, request: RoutingRequest
    ) -> ModelCapabilityProfile | None:
        """Try tiers from start_tier downward to find an affordable model."""
        start_order = _TIER_ORDER.get(start_tier, 2)
        for tier, order in sorted(_TIER_ORDER.items(), key=lambda x: -x[1]):
            if order > start_order:
                continue
            candidates = self._profiles_by_tier.get(tier, [])
            suitable = [p for p in candidates if p.max_context >= request.context_size]
            affordable = [p for p in suitable if p.cost_per_1k_tokens <= request.budget_threshold]
            if affordable:
                affordable.sort(key=lambda p: (p.cost_per_1k_tokens, -p.max_context))
                return affordable[0]
        return None

    @staticmethod
    def _complexity_to_tier(complexity: TaskComplexity) -> ModelTier:
        return {
            TaskComplexity.SIMPLE: ModelTier.SMALL,
            TaskComplexity.MODERATE: ModelTier.MID,
            TaskComplexity.COMPLEX: ModelTier.HIGH,
        }.get(complexity, ModelTier.SMALL)

    # ------------------------------------------------------------------
    # Model selection within a tier
    # ------------------------------------------------------------------

    def _select_from_tier(
        self, tier: ModelTier, request: RoutingRequest
    ) -> ModelCapabilityProfile | None:
        """Select the best model within a tier that satisfies the request."""
        candidates = self._profiles_by_tier.get(tier, [])
        if not candidates:
            return None

        # Filter by context window
        suitable = [p for p in candidates if p.max_context >= request.context_size]
        if not suitable:
            return None

        # Filter by budget
        if request.budget_threshold < float("inf"):
            affordable = [p for p in suitable if p.cost_per_1k_tokens <= request.budget_threshold]
            if affordable:
                suitable = affordable

        # Filter by reflection capability if needed
        if request.required_reflection:
            reflective = [p for p in suitable if p.reflection_passes > 0]
            if reflective:
                suitable = reflective

        # Prefer cheapest model that fits (cost-aware selection)
        suitable.sort(key=lambda p: (p.cost_per_1k_tokens, -p.max_context))
        return suitable[0]

    def _escalate(
        self, from_tier: ModelTier, request: RoutingRequest
    ) -> ModelCapabilityProfile | None:
        """Try higher tiers if no model found in the target tier."""
        current_order = _TIER_ORDER.get(from_tier, 0)
        for tier, order in sorted(_TIER_ORDER.items(), key=lambda x: x[1]):
            if order <= current_order:
                continue
            result = self._select_from_tier(tier, request)
            if result:
                logger.info("capability_router escalated from=%s to=%s", from_tier.value, tier.value)
                return result
        return None

    def _fallback_any(self, request: RoutingRequest) -> ModelCapabilityProfile | None:
        """Last resort: pick any model with the largest context window."""
        if not self._profiles:
            return None
        return max(self._profiles, key=lambda p: p.max_context)

    def _find_fallback(
        self, selected: ModelCapabilityProfile, request: RoutingRequest
    ) -> ModelCapabilityProfile | None:
        """Find a cheaper fallback model in a lower tier."""
        selected_order = _TIER_ORDER.get(selected.tier, 0)
        for tier, order in sorted(_TIER_ORDER.items(), key=lambda x: x[1]):
            if order >= selected_order:
                continue
            candidates = self._profiles_by_tier.get(tier, [])
            suitable = [p for p in candidates if p.max_context >= request.context_size]
            if suitable:
                suitable.sort(key=lambda p: p.cost_per_1k_tokens)
                return suitable[0]
        return None

    def _apply_budget_constraint(
        self, tier: ModelTier, budget: float
    ) -> ModelTier:
        """If no model in tier is affordable, drop to cheaper tier."""
        candidates = self._profiles_by_tier.get(tier, [])
        affordable = [p for p in candidates if p.cost_per_1k_tokens <= budget]
        if affordable:
            return tier

        # Try cheaper tiers
        current_order = _TIER_ORDER.get(tier, 0)
        for t, order in sorted(_TIER_ORDER.items(), key=lambda x: -x[1]):
            if order >= current_order:
                continue
            candidates = self._profiles_by_tier.get(t, [])
            affordable = [p for p in candidates if p.cost_per_1k_tokens <= budget]
            if affordable:
                logger.info("budget_constraint downgraded from=%s to=%s budget=%.4f", tier.value, t.value, budget)
                return t

        return tier  # No cheaper option, keep original

    # ------------------------------------------------------------------
    # Config loading
    # ------------------------------------------------------------------

    def _load_profiles(self) -> None:
        if not self._models_path.exists():
            logger.warning("models_config not found at %s", self._models_path)
            return
        try:
            data = json.loads(self._models_path.read_text(encoding="utf-8"))
            for entry in data.get("models", []):
                profile = ModelCapabilityProfile.model_validate(entry)
                self._profiles.append(profile)
                self._profiles_by_tier.setdefault(profile.tier, []).append(profile)
            logger.info("capability_router loaded %d model profiles", len(self._profiles))
        except Exception:
            logger.exception("capability_router profile_load_failed path=%s", self._models_path)

    def _load_rules(self) -> None:
        if not self._rules_path.exists():
            logger.warning("routing_rules not found at %s", self._rules_path)
            return
        try:
            self._rules = json.loads(self._rules_path.read_text(encoding="utf-8"))
            logger.info("capability_router loaded routing rules with %d rules", len(self._rules.get("rules", [])))
        except Exception:
            logger.exception("capability_router rules_load_failed path=%s", self._rules_path)
