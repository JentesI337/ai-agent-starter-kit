from __future__ import annotations

import asyncio

from app.config import settings
from app.tools.implementations.base import AgentTooling
from app.tools.implementations.web import WebSearchResponse, WebSearchResult


def test_agent_tooling_web_search_formats_results(monkeypatch, tmp_path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))

    async def fake_search(self, query: str, *, max_results: int = 5):
        _ = (self, max_results)
        return WebSearchResponse(
            query=query,
            results=[
                WebSearchResult(
                    title="Paris - Wikipedia",
                    url="https://en.wikipedia.org/wiki/Paris",
                    snippet="Paris is the capital and largest city of France.",
                    source="organic",
                    relevance_score=0.92,
                )
            ],
            total_results=1,
            search_time_ms=12.3,
            provider="duckduckgo",
        )

    monkeypatch.setattr("app.tools.implementations.web_search.WebSearchService.search", fake_search)
    monkeypatch.setattr(settings, "web_search_provider", "duckduckgo")
    monkeypatch.setattr(settings, "web_search_api_key", "")
    monkeypatch.setattr(settings, "web_search_base_url", "")

    output = asyncio.run(tooling.web_search("capital of france", max_results=3))

    assert "query: capital of france" in output
    assert "provider: duckduckgo" in output
    assert "source_url: https://en.wikipedia.org/wiki/Paris" in output
    assert "Paris is the capital" in output
