"""Thin wrapper around ChromaDB for RAG vector storage.

Provides CRUD operations on collections and nearest-neighbour query
using pre-computed embeddings from EmbeddingService.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    _HAS_CHROMADB = True
except ImportError:
    chromadb = None  # type: ignore[assignment]
    ChromaSettings = None  # type: ignore[assignment,misc]
    _HAS_CHROMADB = False

logger = logging.getLogger("app.services.vector_store")

# Hard ceiling on stored chunks per collection
MAX_CHUNKS_PER_COLLECTION = 10_000


@dataclass
class QueryResult:
    """A single query hit."""
    text: str
    source: str
    score: float
    chunk_index: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CollectionStats:
    """Basic stats for a collection."""
    name: str
    count: int


class VectorStoreError(Exception):
    """Raised on vector store failures."""


class VectorStore:
    """ChromaDB-backed vector store for RAG chunks."""

    def __init__(
        self,
        persist_dir: str = "./chroma_data",
        *,
        max_chunks_per_collection: int = MAX_CHUNKS_PER_COLLECTION,
    ) -> None:
        if not _HAS_CHROMADB:
            raise VectorStoreError(
                "chromadb is not installed. Install it with: pip install chromadb"
            )
        self._persist_dir = persist_dir
        self._max_chunks = max_chunks_per_collection
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        logger.info("VectorStore initialised (persist_dir=%s)", persist_dir)

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    def create_collection(self, name: str) -> None:
        """Create a new collection (or get existing one)."""
        self._client.get_or_create_collection(name=name)
        logger.info("Collection created/verified: %s", name)

    def delete_collection(self, name: str) -> None:
        """Delete a collection."""
        try:
            self._client.delete_collection(name=name)
            logger.info("Collection deleted: %s", name)
        except Exception as exc:
            raise VectorStoreError(f"Failed to delete collection '{name}': {exc}") from exc

    def list_collections(self) -> list[CollectionStats]:
        """List all collections with their document counts."""
        collections = self._client.list_collections()
        stats: list[CollectionStats] = []
        for name in collections:
            col_name = name if isinstance(name, str) else name.name
            col = self._client.get_collection(col_name)
            stats.append(CollectionStats(name=col_name, count=col.count()))
        return stats

    def collection_stats(self, name: str) -> CollectionStats:
        """Get stats for a single collection."""
        try:
            col = self._client.get_collection(name)
            return CollectionStats(name=name, count=col.count())
        except Exception as exc:
            raise VectorStoreError(f"Collection '{name}' not found: {exc}") from exc

    # ------------------------------------------------------------------
    # Add documents
    # ------------------------------------------------------------------

    def add(
        self,
        collection_name: str,
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
    ) -> int:
        """Add chunks with pre-computed embeddings to a collection.

        Returns:
            Number of chunks actually added.
        """
        col = self._client.get_or_create_collection(name=collection_name)
        current_count = col.count()
        remaining = self._max_chunks - current_count
        if remaining <= 0:
            logger.warning(
                "Collection '%s' is at capacity (%d/%d)",
                collection_name, current_count, self._max_chunks,
            )
            return 0

        # Trim to remaining capacity
        n = min(len(texts), remaining)
        texts = texts[:n]
        embeddings = embeddings[:n]

        if ids is None:
            ids = [f"{collection_name}-{current_count + i}" for i in range(n)]
        else:
            ids = ids[:n]

        if metadatas is not None:
            metadatas = metadatas[:n]
        else:
            metadatas = [{"_idx": str(i)} for i in range(n)]

        # ChromaDB metadata values must be str, int, float, or bool
        # and metadata dicts must be non-empty
        clean_metas: list[dict[str, Any]] = []
        for i, m in enumerate(metadatas):
            clean: dict[str, Any] = {}
            for k, v in m.items():
                if isinstance(v, (str, int, float, bool)):
                    clean[k] = v
                else:
                    clean[k] = str(v)
            if not clean:
                clean["_idx"] = str(i)
            clean_metas.append(clean)

        col.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=clean_metas,
        )
        logger.info(
            "Added %d chunks to '%s' (total: %d)",
            n, collection_name, current_count + n,
        )
        return n

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(
        self,
        collection_name: str,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[QueryResult]:
        """Find nearest chunks to a query embedding."""
        try:
            col = self._client.get_collection(collection_name)
        except Exception as exc:
            raise VectorStoreError(f"Collection '{collection_name}' not found: {exc}") from exc

        if col.count() == 0:
            return []

        top_k = min(top_k, col.count())
        results = col.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        hits: list[QueryResult] = []
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for doc, meta, dist in zip(documents, metadatas, distances):
            meta = meta or {}
            hits.append(QueryResult(
                text=doc or "",
                source=str(meta.get("source", "")),
                score=1.0 - dist if dist <= 1.0 else 1.0 / (1.0 + dist),
                chunk_index=int(meta.get("chunk_index", 0)),
                metadata=meta,
            ))

        return hits
