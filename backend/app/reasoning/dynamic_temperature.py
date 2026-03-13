from __future__ import annotations

TEMPERATURE_BY_TASK_TYPE: dict[str, float] = {
    "hard_research": 0.1,
    "research": 0.15,
    "implementation": 0.15,
    "orchestration": 0.2,
    "orchestration_failed": 0.2,
    "orchestration_pending": 0.2,
    "general": 0.3,
    "trivial": 0.4,
}


class DynamicTemperatureResolver:
    def __init__(self, base_temperature: float, overrides: dict[str, float] | None = None, *, reasoning_delta: float = 0.05):
        self._base = self._clamp(base_temperature)
        merged = {**TEMPERATURE_BY_TASK_TYPE, **(overrides or {})}
        self._overrides = {str(key).strip().lower(): self._clamp(value) for key, value in merged.items() if str(key).strip()}
        self._reasoning_delta = max(0.0, min(0.5, float(reasoning_delta)))

    @staticmethod
    def _clamp(value: float) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, numeric))

    def resolve(self, task_type: str | None, *, reasoning_level: str | None = None) -> float:
        normalized_task = (task_type or "").strip().lower()
        base = self._overrides.get(normalized_task, self._base)

        normalized_reasoning = (reasoning_level or "").strip().lower()
        if normalized_reasoning in {"high", "ultrathink"}:
            return self._clamp(base - self._reasoning_delta)
        if normalized_reasoning == "low":
            return self._clamp(base + self._reasoning_delta)
        return self._clamp(base)
