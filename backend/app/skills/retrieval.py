from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
import re

from app.skills.models import SkillSnapshot


@dataclass(frozen=True)
class RetrievalSource:
    source_id: str
    title: str
    location: str
    score: float
    trust: float
    reason: str


@dataclass(frozen=True)
class RetrievalResult:
    query: str
    sources: tuple[RetrievalSource, ...]
    from_cache: bool

    @property
    def has_sources(self) -> bool:
        return len(self.sources) > 0


@dataclass(frozen=True)
class ReliableRetrievalConfig:
    enabled: bool
    max_sources: int
    min_score: float
    cache_ttl_seconds: float
    default_source_trust: float


@dataclass(frozen=True)
class _CacheEntry:
    query_key: str
    snapshot_key: str
    result: RetrievalResult
    created_at: float


class ReliableRetrievalService:
    def __init__(self, config: ReliableRetrievalConfig):
        self._config = config
        self._cache: _CacheEntry | None = None

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-zA-Z0-9_\-]{2,}", (text or "").lower())
            if token
        }

    @staticmethod
    def _jaccard(a: set[str], b: set[str]) -> float:
        if not a and not b:
            return 0.0
        union = a | b
        if not union:
            return 0.0
        return len(a & b) / len(union)

    @staticmethod
    def _snapshot_key(snapshot: SkillSnapshot) -> str:
        return "|".join(
            [
                str(snapshot.discovered_count),
                str(snapshot.eligible_count),
                str(snapshot.selected_count),
                "1" if snapshot.truncated else "0",
                str(len(snapshot.skills)),
            ]
        )

    def _cache_hit(self, *, query_key: str, snapshot_key: str) -> RetrievalResult | None:
        entry = self._cache
        if entry is None:
            return None
        if self._config.cache_ttl_seconds <= 0:
            return None
        if monotonic() - entry.created_at > self._config.cache_ttl_seconds:
            return None
        if entry.query_key != query_key or entry.snapshot_key != snapshot_key:
            return None
        return RetrievalResult(query=entry.result.query, sources=entry.result.sources, from_cache=True)

    def _cache_write(self, *, query_key: str, snapshot_key: str, result: RetrievalResult) -> None:
        if self._config.cache_ttl_seconds <= 0:
            return
        self._cache = _CacheEntry(
            query_key=query_key,
            snapshot_key=snapshot_key,
            result=result,
            created_at=monotonic(),
        )

    def retrieve(self, *, query: str, snapshot: SkillSnapshot) -> RetrievalResult:
        normalized_query = (query or "").strip()
        if not self._config.enabled or not normalized_query:
            return RetrievalResult(query=normalized_query, sources=(), from_cache=False)

        query_tokens = self._tokenize(normalized_query)
        if not query_tokens:
            return RetrievalResult(query=normalized_query, sources=(), from_cache=False)

        query_key = " ".join(sorted(query_tokens))
        snapshot_key = self._snapshot_key(snapshot)
        cached = self._cache_hit(query_key=query_key, snapshot_key=snapshot_key)
        if cached is not None:
            return cached

        scored_sources: list[RetrievalSource] = []
        for index, raw in enumerate(snapshot.skills):
            name = str(raw.get("name") or "").strip()
            description = str(raw.get("description") or "").strip()
            location = str(raw.get("file_path") or "").strip()
            if not name and not description:
                continue

            text = f"{name} {description} {location}"
            source_tokens = self._tokenize(text)
            score = self._jaccard(query_tokens, source_tokens)
            if score < self._config.min_score:
                continue

            overlap = sorted(query_tokens & source_tokens)
            reason = ",".join(overlap[:5]) if overlap else "semantic_overlap"
            scored_sources.append(
                RetrievalSource(
                    source_id=f"skill:{index + 1}",
                    title=name or f"skill-{index + 1}",
                    location=location,
                    score=round(score, 4),
                    trust=max(0.0, min(1.0, float(self._config.default_source_trust))),
                    reason=reason,
                )
            )

        scored_sources.sort(key=lambda item: (item.score, item.trust), reverse=True)
        limited = tuple(scored_sources[: max(1, int(self._config.max_sources))])
        result = RetrievalResult(query=normalized_query, sources=limited, from_cache=False)
        self._cache_write(query_key=query_key, snapshot_key=snapshot_key, result=result)
        return result


def format_retrieval_sources_for_prompt(result: RetrievalResult) -> str:
    if not result.sources:
        return ""
    lines = [
        "Reliable retrieval sources (use these first, then read exact SKILL.md files when needed):",
    ]
    for source in result.sources:
        lines.append(
            f"- {source.title} | location={source.location or '(n/a)'} | trust={source.trust:.2f} | score={source.score:.3f} | reason={source.reason}"
        )
    return "\n".join(lines).strip()
