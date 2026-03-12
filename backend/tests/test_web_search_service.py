from __future__ import annotations

import asyncio

import pytest

from app.tools.implementations.web import WebSearchService


class _StubService(WebSearchService):
    def __init__(self, provider: str, payload: dict):
        super().__init__(provider=provider, api_key="test-key", base_url="https://example.test")
        self._payload = payload

    async def _request_json(self, method: str, url: str, *, headers=None, params=None, json_body=None) -> dict:
        _ = (method, url, headers, params, json_body)
        return self._payload


def test_duckduckgo_parses_related_topics() -> None:
    service = _StubService(
        "duckduckgo",
        {
            "AbstractURL": "https://en.wikipedia.org/wiki/France",
            "AbstractText": "France is a country in Europe.",
            "Heading": "France",
            "RelatedTopics": [{"Text": "Paris - Capital city of France", "FirstURL": "https://duckduckgo.com/Paris"}],
        },
    )

    response = asyncio.run(service.search("capital of france", max_results=3))

    assert response.provider == "duckduckgo"
    assert response.total_results >= 1
    assert any(result.url for result in response.results)


def test_searxng_parses_standard_results() -> None:
    service = _StubService(
        "searxng",
        {
            "results": [
                {
                    "title": "Paris",
                    "url": "https://example.com/paris",
                    "content": "Paris is the capital of France.",
                }
            ]
        },
    )

    response = asyncio.run(service.search("capital of france", max_results=5))

    assert response.provider == "searxng"
    assert response.total_results == 1
    assert response.results[0].title == "Paris"
    assert response.results[0].url == "https://example.com/paris"


def test_unknown_provider_raises_value_error() -> None:
    service = WebSearchService(provider="unknown", api_key=None, base_url=None)

    with pytest.raises(ValueError, match="Unknown search provider"):
        asyncio.run(service.search("test"))
