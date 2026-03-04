from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import settings
from app.services.reflection_feedback_store import ReflectionFeedbackStore


@dataclass(frozen=True)
class CalibrationRecommendation:
    parameter: str
    current_value: float
    recommended_value: float
    confidence: float
    evidence: str


class BenchmarkCalibrationService:
    def __init__(
        self,
        *,
        reflection_feedback_store: ReflectionFeedbackStore,
        model_health_tracker: Any | None = None,
        recovery_metrics_path: str | None = None,
        min_samples: int = 20,
    ) -> None:
        self._reflection_feedback_store = reflection_feedback_store
        self._model_health_tracker = model_health_tracker
        self._recovery_metrics_path = Path(recovery_metrics_path) if recovery_metrics_path else None
        self._min_samples = max(1, int(min_samples))

    def analyze(self) -> list[CalibrationRecommendation]:
        recommendations: list[CalibrationRecommendation] = []
        recommendations.extend(self._recommend_from_reflection())
        recommendations.extend(self._recommend_from_model_health())
        recommendations.extend(self._recommend_from_recovery_metrics())
        return recommendations

    def _recommend_from_reflection(self) -> list[CalibrationRecommendation]:
        averages = self._reflection_feedback_store.get_avg_scores_by_task_type(last_n=200)
        result: list[CalibrationRecommendation] = []
        for task_type, metrics in averages.items():
            samples = int(float(metrics.get("samples", 0.0)))
            if samples < self._min_samples:
                continue
            score = float(metrics.get("score", 0.0))
            if score >= 0.7:
                continue

            current = float(settings.reflection_threshold)
            target = max(0.5, min(0.85, current - 0.05))
            confidence = max(0.2, min(1.0, samples / float(max(self._min_samples, 100))))
            result.append(
                CalibrationRecommendation(
                    parameter="REFLECTION_THRESHOLD",
                    current_value=current,
                    recommended_value=target,
                    confidence=round(confidence, 3),
                    evidence=f"task_type={task_type} avg_score={score:.3f} samples={samples}",
                )
            )
        return result

    def _recommend_from_model_health(self) -> list[CalibrationRecommendation]:
        tracker = self._model_health_tracker
        if tracker is None:
            return []

        snapshots = []
        try:
            snapshots = list(tracker.all_snapshots())
        except Exception:
            snapshots = []

        if not snapshots:
            return []

        high_latency = [s for s in snapshots if int(getattr(s, "sample_count", 0)) >= self._min_samples and int(getattr(s, "p95_latency_ms", 0)) >= 2500]
        low_health = [s for s in snapshots if int(getattr(s, "sample_count", 0)) >= self._min_samples and float(getattr(s, "health_score", 1.0)) < 0.7]

        recommendations: list[CalibrationRecommendation] = []
        if high_latency:
            current = float(settings.model_score_weight_latency)
            recommendations.append(
                CalibrationRecommendation(
                    parameter="MODEL_SCORE_WEIGHT_LATENCY",
                    current_value=current,
                    recommended_value=round(min(0.05, current * 1.25), 5),
                    confidence=round(min(1.0, len(high_latency) / 5.0), 3),
                    evidence=f"high_p95_models={len(high_latency)} threshold_ms=2500",
                )
            )
        if low_health:
            current = float(settings.model_score_weight_health)
            recommendations.append(
                CalibrationRecommendation(
                    parameter="MODEL_SCORE_WEIGHT_HEALTH",
                    current_value=current,
                    recommended_value=round(min(200.0, current * 1.1), 3),
                    confidence=round(min(1.0, len(low_health) / 5.0), 3),
                    evidence=f"low_health_models={len(low_health)} threshold=0.7",
                )
            )
        return recommendations

    def _recommend_from_recovery_metrics(self) -> list[CalibrationRecommendation]:
        metrics_path = self._recovery_metrics_path
        if metrics_path is None or not metrics_path.exists():
            return []

        try:
            payload = json.loads(metrics_path.read_text(encoding="utf-8"))
        except Exception:
            return []

        metrics_root = payload.get("metrics") if isinstance(payload, dict) else None
        if not isinstance(metrics_root, dict):
            return []

        strategy_totals: dict[str, dict[str, int]] = {}
        for reason_bucket in metrics_root.values():
            if not isinstance(reason_bucket, dict):
                continue
            for model_bucket in reason_bucket.values():
                if not isinstance(model_bucket, dict):
                    continue
                for strategy, counts in model_bucket.items():
                    if not isinstance(counts, dict):
                        continue
                    success = max(0, int(counts.get("success", 0) or 0))
                    failure = max(0, int(counts.get("failure", 0) or 0))
                    bucket = strategy_totals.setdefault(str(strategy), {"success": 0, "failure": 0})
                    bucket["success"] += success
                    bucket["failure"] += failure

        if not strategy_totals:
            return []

        best_strategy = None
        best_rate = -1.0
        best_samples = 0
        for strategy, totals in strategy_totals.items():
            samples = totals["success"] + totals["failure"]
            if samples < self._min_samples:
                continue
            rate = totals["success"] / float(samples)
            if rate > best_rate:
                best_rate = rate
                best_strategy = strategy
                best_samples = samples

        if best_strategy is None:
            return []

        current = 1.0
        recommended = 1.0
        if "fallback_retry" in best_strategy:
            current = float(settings.model_score_runtime_bonus)
            recommended = min(20.0, current + 1.0)

        return [
            CalibrationRecommendation(
                parameter="MODEL_SCORE_RUNTIME_BONUS",
                current_value=current,
                recommended_value=round(recommended, 3),
                confidence=round(min(1.0, best_samples / 100.0), 3),
                evidence=f"best_recovery_strategy={best_strategy} success_rate={best_rate:.3f} samples={best_samples}",
            )
        ]

    def export_env_patch(self, recommendations: list[CalibrationRecommendation]) -> str:
        lines = [
            f"{item.parameter}={item.recommended_value}"
            for item in recommendations
            if str(item.parameter or "").strip()
        ]
        return "\n".join(lines)
