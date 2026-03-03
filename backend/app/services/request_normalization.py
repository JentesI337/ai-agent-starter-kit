from __future__ import annotations

from app.errors import GuardrailViolation


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
