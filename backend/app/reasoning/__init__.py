"""Reasoning domain — parsing, intent detection, normalization, and prompt building."""

from app.reasoning.action_parser import ActionParser
from app.reasoning.dynamic_temperature import DynamicTemperatureResolver
from app.reasoning.intent_detector import IntentDetector, IntentGateDecision
from app.reasoning.plan_graph import PlanGraph, PlanStep
from app.reasoning.reply_shaper import ReplyShaper, ReplyShapeResult
from app.reasoning.request_normalization import (
    normalize_idempotency_key,
    normalize_preset,
    normalize_prompt_mode,
    normalize_queue_mode,
)


# Lazy imports for modules with dependency chains that could cause circular imports.
def __getattr__(name: str):
    if name == "ActionAugmenter":
        from app.reasoning.action_augmenter import ActionAugmenter

        return ActionAugmenter

    if name in (
        "DirectiveParseResult",
        "DirectiveOverrides",
        "parse_directives_from_message",
        "normalize_reasoning_level",
        "normalize_reasoning_visibility",
    ):
        from app.reasoning import directive_parser as _dp

        return getattr(_dp, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ActionAugmenter",
    "ActionParser",
    "DirectiveOverrides",
    "DirectiveParseResult",
    "DynamicTemperatureResolver",
    "IntentDetector",
    "IntentGateDecision",
    "PlanGraph",
    "PlanStep",
    "ReplyShapeResult",
    "ReplyShaper",
    "normalize_idempotency_key",
    "normalize_preset",
    "normalize_prompt_mode",
    "normalize_queue_mode",
    "normalize_reasoning_level",
    "normalize_reasoning_visibility",
    "parse_directives_from_message",
]
