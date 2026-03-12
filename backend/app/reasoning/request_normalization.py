from __future__ import annotations

from app.errors import GuardrailViolation

QUEUE_MODE_VALUES = ("wait", "follow_up", "steer")
PROMPT_MODE_VALUES = ("full", "minimal", "subagent")


def normalize_preset(value: str | None) -> str | None:
    preset = (value or "").strip().lower()
    return preset or None


def normalize_idempotency_key(value: str | None, *, max_length: int = 200) -> str | None:
    key = (value or "").strip()
    if not key:
        return None
    if len(key) > max_length:
        raise GuardrailViolation(f"Idempotency key too long (max {max_length}).")
    return key


def normalize_queue_mode(value: str | None, *, default: str = "wait") -> str:
    normalized_default = (default or "wait").strip().lower() or "wait"
    if normalized_default not in QUEUE_MODE_VALUES:
        normalized_default = "wait"

    normalized = (value or "").strip().lower()
    if not normalized:
        return normalized_default
    if normalized not in QUEUE_MODE_VALUES:
        raise GuardrailViolation(
            "Unsupported queue_mode. Allowed values: wait, follow_up, steer."
        )
    return normalized


def normalize_prompt_mode(value: str | None, *, default: str = "full") -> str:
    normalized_default = (default or "full").strip().lower() or "full"
    if normalized_default not in PROMPT_MODE_VALUES:
        normalized_default = "full"

    normalized = (value or "").strip().lower()
    if not normalized:
        return normalized_default
    if normalized not in PROMPT_MODE_VALUES:
        raise GuardrailViolation(
            "Unsupported prompt_mode. Allowed values: full, minimal, subagent."
        )
    return normalized
