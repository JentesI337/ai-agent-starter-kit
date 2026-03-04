from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PromptVariant:
    variant_id: str
    prompt_text: str
    weight: float


class PromptAbRegistry:
    def __init__(self, registry_path: str):
        self._registry_path = Path(registry_path)
        self._cache: dict[str, list[PromptVariant]] = {}
        self._last_mtime: float | None = None

    def _normalize_weight(self, value: object) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, numeric))

    def _reload_if_needed(self) -> None:
        try:
            mtime = self._registry_path.stat().st_mtime
        except OSError:
            self._cache = {}
            self._last_mtime = None
            return

        if self._last_mtime is not None and mtime == self._last_mtime:
            return

        try:
            payload = json.loads(self._registry_path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("prompt_ab_registry_load_failed", exc_info=True)
            self._cache = {}
            self._last_mtime = mtime
            return

        if not isinstance(payload, dict):
            self._cache = {}
            self._last_mtime = mtime
            return

        parsed: dict[str, list[PromptVariant]] = {}
        for group_key, raw_variants in payload.items():
            normalized_group = str(group_key or "").strip()
            if not normalized_group or not isinstance(raw_variants, list):
                continue

            variants: list[PromptVariant] = []
            for item in raw_variants:
                if not isinstance(item, dict):
                    continue
                variant_id = str(item.get("variant_id") or "").strip()
                prompt_text = str(item.get("prompt_text") or "").strip()
                weight = self._normalize_weight(item.get("weight", 0.0))
                if not variant_id or not prompt_text or weight <= 0.0:
                    continue
                variants.append(PromptVariant(variant_id=variant_id, prompt_text=prompt_text, weight=weight))

            if not variants:
                continue

            total = sum(variant.weight for variant in variants)
            if total <= 0:
                continue
            parsed[normalized_group] = [
                PromptVariant(
                    variant_id=variant.variant_id,
                    prompt_text=variant.prompt_text,
                    weight=variant.weight / total,
                )
                for variant in variants
            ]

        self._cache = parsed
        self._last_mtime = mtime

    @staticmethod
    def _deterministic_bucket(*, group: str, session_id: str) -> float:
        key = f"{group}:{session_id}".encode("utf-8", errors="ignore")
        digest = hashlib.sha256(key).hexdigest()
        value = int(digest[:16], 16)
        max_value = float(0xFFFFFFFFFFFFFFFF)
        return value / max_value if max_value > 0 else 0.0

    def select(self, group: str, session_id: str) -> PromptVariant | None:
        self._reload_if_needed()

        normalized_group = (group or "").strip()
        normalized_session = (session_id or "").strip()
        if not normalized_group or not normalized_session:
            return None

        variants = self._cache.get(normalized_group)
        if not variants:
            return None

        bucket = self._deterministic_bucket(group=normalized_group, session_id=normalized_session)
        cumulative = 0.0
        for variant in variants:
            cumulative += variant.weight
            if bucket <= cumulative:
                return variant
        return variants[-1]
