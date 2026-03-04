from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from urllib.parse import quote_plus

import httpx


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str
    source: str
    relevance_score: float


@dataclass(frozen=True)
class WebSearchResponse:
    query: str
    results: list[WebSearchResult]
    total_results: int
    search_time_ms: float
    provider: str


class WebSearchService:
    def __init__(self, provider: str, api_key: str | None, base_url: str | None):
        normalized_provider = (provider or "duckduckgo").strip().lower()
        self.provider = normalized_provider or "duckduckgo"
        self.api_key = (api_key or "").strip() or None
        self.base_url = (base_url or "").strip() or None

    async def search(self, query: str, *, max_results: int = 5) -> WebSearchResponse:
        normalized_query = (query or "").strip()
        if not normalized_query:
            raise ValueError("query must not be empty")
        bounded_max_results = max(1, min(int(max_results), 10))

        started = monotonic()
        if self.provider == "searxng":
            results = await self._search_searxng(normalized_query, bounded_max_results)
        elif self.provider == "tavily":
            results = await self._search_tavily(normalized_query, bounded_max_results)
        elif self.provider == "brave":
            results = await self._search_brave(normalized_query, bounded_max_results)
        elif self.provider == "duckduckgo":
            results = await self._search_duckduckgo(normalized_query, bounded_max_results)
        else:
            raise ValueError(f"Unknown search provider: {self.provider}")

        duration_ms = round((monotonic() - started) * 1000, 2)
        return WebSearchResponse(
            query=normalized_query,
            results=results,
            total_results=len(results),
            search_time_ms=duration_ms,
            provider=self.provider,
        )

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, object] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> dict:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_body,
            )
            response.raise_for_status()
            payload = response.json()
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _normalize_result(
        *,
        title: str,
        url: str,
        snippet: str,
        source: str = "organic",
        relevance_score: float = 0.0,
    ) -> WebSearchResult:
        cleaned_title = (title or "").strip() or "(untitled)"
        cleaned_url = (url or "").strip()
        cleaned_snippet = (snippet or "").strip()
        score = max(0.0, min(1.0, float(relevance_score)))
        return WebSearchResult(
            title=cleaned_title,
            url=cleaned_url,
            snippet=cleaned_snippet,
            source=(source or "organic").strip() or "organic",
            relevance_score=score,
        )

    async def _search_searxng(self, query: str, max_results: int) -> list[WebSearchResult]:
        base_url = self.base_url or "http://localhost:8080"
        payload = await self._request_json(
            "GET",
            f"{base_url.rstrip('/')}/search",
            params={
                "q": query,
                "format": "json",
                "engines": "google,bing,duckduckgo",
                "pageno": 1,
            },
        )
        raw_results = payload.get("results") if isinstance(payload.get("results"), list) else []
        results: list[WebSearchResult] = []
        for item in raw_results[:max_results]:
            if not isinstance(item, dict):
                continue
            results.append(
                self._normalize_result(
                    title=str(item.get("title", "")),
                    url=str(item.get("url", "")),
                    snippet=str(item.get("content", item.get("snippet", ""))),
                    source="organic",
                    relevance_score=0.7,
                )
            )
        return [result for result in results if result.url]

    async def _search_tavily(self, query: str, max_results: int) -> list[WebSearchResult]:
        if not self.api_key:
            raise ValueError("WEB_SEARCH_API_KEY is required for tavily provider")
        payload = await self._request_json(
            "POST",
            self.base_url or "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json_body={
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
                "include_answer": False,
                "include_images": False,
            },
        )
        raw_results = payload.get("results") if isinstance(payload.get("results"), list) else []
        results: list[WebSearchResult] = []
        for item in raw_results[:max_results]:
            if not isinstance(item, dict):
                continue
            results.append(
                self._normalize_result(
                    title=str(item.get("title", "")),
                    url=str(item.get("url", "")),
                    snippet=str(item.get("content", "")),
                    source="organic",
                    relevance_score=float(item.get("score", 0.7) or 0.7),
                )
            )
        return [result for result in results if result.url]

    async def _search_brave(self, query: str, max_results: int) -> list[WebSearchResult]:
        if not self.api_key:
            raise ValueError("WEB_SEARCH_API_KEY is required for brave provider")
        payload = await self._request_json(
            "GET",
            self.base_url or "https://api.search.brave.com/res/v1/web/search",
            headers={
                "X-Subscription-Token": self.api_key,
                "Accept": "application/json",
            },
            params={"q": query, "count": max_results},
        )
        web_block = payload.get("web") if isinstance(payload.get("web"), dict) else {}
        raw_results = web_block.get("results") if isinstance(web_block.get("results"), list) else []
        results: list[WebSearchResult] = []
        for item in raw_results[:max_results]:
            if not isinstance(item, dict):
                continue
            results.append(
                self._normalize_result(
                    title=str(item.get("title", "")),
                    url=str(item.get("url", "")),
                    snippet=str(item.get("description", item.get("snippet", ""))),
                    source="organic",
                    relevance_score=0.7,
                )
            )
        return [result for result in results if result.url]

    async def _search_duckduckgo(self, query: str, max_results: int) -> list[WebSearchResult]:
        payload = await self._request_json(
            "GET",
            self.base_url or "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_redirect": 1, "no_html": 1},
        )

        results: list[WebSearchResult] = []
        abstract_url = str(payload.get("AbstractURL", "")).strip()
        abstract_text = str(payload.get("AbstractText", "")).strip()
        heading = str(payload.get("Heading", "")).strip()
        if abstract_url and abstract_text:
            results.append(
                self._normalize_result(
                    title=heading or "DuckDuckGo Abstract",
                    url=abstract_url,
                    snippet=abstract_text,
                    source="answer_box",
                    relevance_score=0.75,
                )
            )

        related = payload.get("RelatedTopics") if isinstance(payload.get("RelatedTopics"), list) else []
        for item in related:
            if len(results) >= max_results:
                break
            if isinstance(item, dict) and isinstance(item.get("Topics"), list):
                nested_topics = item.get("Topics")
            else:
                nested_topics = [item]

            for topic in nested_topics:
                if len(results) >= max_results:
                    break
                if not isinstance(topic, dict):
                    continue
                topic_url = str(topic.get("FirstURL", "")).strip()
                topic_text = str(topic.get("Text", "")).strip()
                if not topic_url or not topic_text:
                    continue
                title = topic_text.split(" - ")[0].strip() or "DuckDuckGo Result"
                results.append(
                    self._normalize_result(
                        title=title,
                        url=topic_url,
                        snippet=topic_text,
                        source="organic",
                        relevance_score=0.6,
                    )
                )

        if not results:
            html_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
            results.append(
                self._normalize_result(
                    title=f"DuckDuckGo results for '{query}'",
                    url=html_url,
                    snippet="No instant answer payload returned; use this results page for follow-up fetch.",
                    source="knowledge_panel",
                    relevance_score=0.4,
                )
            )

        return results[:max_results]
