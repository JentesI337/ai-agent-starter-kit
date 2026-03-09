"""Embedding service with provider abstraction, caching, and batch support.

Supports Ollama and OpenAI-compatible embedding APIs.  Provides an LRU
cache to avoid redundant API calls and batch embedding for efficiency.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections import OrderedDict
from typing import Any

import httpx

logger = logging.getLogger("app.services.embedding_service")


class EmbeddingError(RuntimeError):
    """Raised when embedding fails after retries."""


class EmbeddingService:
    """Compute text embeddings via Ollama or OpenAI-compatible APIs.

    Parameters
    ----------
    provider : str
        ``"ollama"`` or ``"openai"``.
    model : str
        Model name (e.g. ``"nomic-embed-text"`` for Ollama).
    base_url : str | None
        API base URL.  Defaults to ``http://localhost:11434`` for Ollama.
    api_key : str | None
        API key (required for OpenAI provider).
    cache_size : int
        Maximum number of cached embeddings.
    max_retries : int
        Number of retry attempts on transient failures.
    """

    def __init__(
        self,
        *,
        provider: str = "ollama",
        model: str = "nomic-embed-text",
        base_url: str | None = None,
        api_key: str | None = None,
        cache_size: int = 1_000,
        max_retries: int = 3,
    ) -> None:
        self.provider = provider.strip().lower()
        self.model = model.strip()
        self.api_key = api_key
        self.max_retries = max(1, max_retries)

        if base_url:
            self.base_url = base_url.rstrip("/")
        elif self.provider == "ollama":
            self.base_url = "http://localhost:11434"
        else:
            self.base_url = "https://api.openai.com"

        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._cache_size = max(0, cache_size)
        self._dimension: int | None = None
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def embed(self, text: str) -> list[float]:
        """Embed a single text string. Returns a vector of floats."""
        key = self._cache_key(text)
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        vectors = await self._call_api([text])
        if not vectors:
            raise EmbeddingError(f"Empty response from {self.provider} embedding API")
        vec = vectors[0]
        self._cache_put(key, vec)
        if self._dimension is None and vec:
            self._dimension = len(vec)
        return vec

    async def embed_batch(self, texts: list[str], batch_size: int = 100) -> list[list[float]]:
        """Embed a batch of texts. Returns a list of vectors."""
        results: list[list[float]] = []
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        # Check cache first
        for i, text in enumerate(texts):
            key = self._cache_key(text)
            cached = self._cache_get(key)
            if cached is not None:
                results.append(cached)
            else:
                results.append([])  # Placeholder
                uncached_indices.append(i)
                uncached_texts.append(text)

        # Process uncached texts in batches
        for start in range(0, len(uncached_texts), batch_size):
            batch = uncached_texts[start : start + batch_size]
            vectors = await self._call_api(batch)
            for j, vec in enumerate(vectors):
                idx = uncached_indices[start + j]
                results[idx] = vec
                self._cache_put(self._cache_key(batch[j]), vec)

        if self._dimension is None:
            for r in results:
                if r:
                    self._dimension = len(r)
                    break

        return results

    def dimension(self) -> int:
        """Return the embedding dimension (available after first embed call)."""
        if self._dimension is None:
            raise EmbeddingError("Dimension unknown — call embed() first.")
        return self._dimension

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Internal: API calls with retry
    # ------------------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers: dict[str, str] = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0),
                headers=headers,
            )
        return self._client

    async def _call_api(self, texts: list[str]) -> list[list[float]]:
        """Call the embedding API with retry logic."""
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                if self.provider == "ollama":
                    return await self._call_ollama(texts)
                elif self.provider == "openai":
                    return await self._call_openai(texts)
                else:
                    raise EmbeddingError(f"Unsupported embedding provider: {self.provider}")
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadTimeout) as exc:
                last_error = exc
                if attempt < self.max_retries - 1:
                    delay = min(2 ** attempt, 8)
                    logger.warning(
                        "embedding_retry attempt=%d/%d delay=%ds error=%s",
                        attempt + 1, self.max_retries, delay, str(exc)[:100],
                    )
                    import asyncio
                    await asyncio.sleep(delay)
        raise EmbeddingError(f"Embedding failed after {self.max_retries} attempts: {last_error}")

    async def _call_ollama(self, texts: list[str]) -> list[list[float]]:
        """Call Ollama /api/embed endpoint."""
        client = await self._get_client()
        url = f"{self.base_url}/api/embed"
        payload: dict[str, Any] = {"model": self.model, "input": texts}
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        embeddings = data.get("embeddings", [])
        if not embeddings:
            raise EmbeddingError(f"Ollama returned no embeddings for model {self.model}")
        return embeddings

    async def _call_openai(self, texts: list[str]) -> list[list[float]]:
        """Call OpenAI-compatible /v1/embeddings endpoint."""
        client = await self._get_client()
        url = f"{self.base_url}/v1/embeddings"
        payload: dict[str, Any] = {"model": self.model, "input": texts}
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("data", [])
        if not items:
            raise EmbeddingError(f"OpenAI returned no embeddings for model {self.model}")
        # Sort by index to ensure correct order
        items.sort(key=lambda x: x.get("index", 0))
        return [item["embedding"] for item in items]

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cache_key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _cache_get(self, key: str) -> list[float] | None:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def _cache_put(self, key: str, value: list[float]) -> None:
        if self._cache_size <= 0:
            return
        self._cache[key] = value
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
