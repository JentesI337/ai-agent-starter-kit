from __future__ import annotations

from app.skills.models import SkillSnapshot
from app.skills.retrieval import (
    ReliableRetrievalConfig,
    ReliableRetrievalService,
    format_retrieval_sources_for_prompt,
)


def _snapshot() -> SkillSnapshot:
    return SkillSnapshot(
        prompt="",
        skills=(
            {
                "name": "python-testing",
                "description": "Run pytest test suite and inspect failures",
                "file_path": "skills/python-testing/SKILL.md",
            },
            {
                "name": "web-research",
                "description": "Fetch trustworthy web sources and summarize",
                "file_path": "skills/web-research/SKILL.md",
            },
        ),
        discovered_count=2,
        eligible_count=2,
        selected_count=2,
        truncated=False,
    )


def test_reliable_retrieval_returns_ranked_sources() -> None:
    service = ReliableRetrievalService(
        ReliableRetrievalConfig(
            enabled=True,
            max_sources=2,
            min_score=0.01,
            cache_ttl_seconds=30,
            default_source_trust=0.8,
        )
    )

    result = service.retrieve(query="run pytest and analyze test failures", snapshot=_snapshot())

    assert result.has_sources is True
    assert result.sources[0].title == "python-testing"
    assert result.sources[0].trust == 0.8


def test_reliable_retrieval_uses_cache_for_same_query_and_snapshot() -> None:
    service = ReliableRetrievalService(
        ReliableRetrievalConfig(
            enabled=True,
            max_sources=2,
            min_score=0.01,
            cache_ttl_seconds=60,
            default_source_trust=0.9,
        )
    )

    first = service.retrieve(query="web source summary", snapshot=_snapshot())
    second = service.retrieve(query="web source summary", snapshot=_snapshot())

    assert first.from_cache is False
    assert second.from_cache is True


def test_format_retrieval_sources_for_prompt_contains_trust_and_score() -> None:
    service = ReliableRetrievalService(
        ReliableRetrievalConfig(
            enabled=True,
            max_sources=1,
            min_score=0.01,
            cache_ttl_seconds=0,
            default_source_trust=0.85,
        )
    )
    result = service.retrieve(query="trustworthy web research", snapshot=_snapshot())

    prompt = format_retrieval_sources_for_prompt(result)

    assert "Reliable retrieval sources" in prompt
    assert "trust=" in prompt
    assert "score=" in prompt
