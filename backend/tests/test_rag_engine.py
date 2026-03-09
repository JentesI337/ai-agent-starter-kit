"""Tests for the RAG engine: Document Chunker, Vector Store, Embedding Service, and RAG tools."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.config import settings
from app.services.document_chunker import (
    Chunk,
    DocumentChunker,
    MAX_FILE_SIZE_BYTES,
    SUPPORTED_EXTENSIONS,
    _approx_token_count,
    _split_by_tokens,
)
from app.services.embedding_service import EmbeddingService, EmbeddingError
from app.services.vector_store import (
    CollectionStats,
    QueryResult,
    VectorStore,
    VectorStoreError,
)
from app.tool_catalog import TOOL_NAMES, TOOL_NAME_SET, TOOL_NAME_ALIASES
from app.tool_policy import TOOL_PROFILES
from app.services.vector_store import _HAS_CHROMADB

_skip_no_chromadb = pytest.mark.skipif(
    not _HAS_CHROMADB, reason="chromadb not installed"
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def chunker() -> DocumentChunker:
    return DocumentChunker()


@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def vector_store(tmp_dir: str) -> VectorStore:
    return VectorStore(persist_dir=os.path.join(tmp_dir, "chroma"), max_chunks_per_collection=100)


def _fake_embedding(text: str, dim: int = 8) -> list[float]:
    """Produce a deterministic fake embedding from text hash."""
    h = hash(text) & 0xFFFFFFFF
    return [((h >> (i * 4)) & 0xF) / 15.0 for i in range(dim)]


# ===========================================================================
# Document Chunker Tests
# ===========================================================================


class TestApproxTokenCount:
    def test_empty(self):
        assert _approx_token_count("") == 0

    def test_single_word(self):
        assert _approx_token_count("hello") == 1  # int(1 * 1.3) = 1

    def test_multi_word(self):
        count = _approx_token_count("the quick brown fox")
        assert count == int(4 * 1.3)  # 5


class TestSplitByTokens:
    def test_empty(self):
        assert _split_by_tokens("", 100, 10) == []

    def test_fits_in_one_chunk(self):
        text = "hello world foo bar"
        chunks = _split_by_tokens(text, 100, 10)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_multiple_chunks(self):
        words = " ".join(f"w{i}" for i in range(200))
        chunks = _split_by_tokens(words, 50, 10)
        assert len(chunks) > 1
        # All words should be recoverable
        all_words = set()
        for c in chunks:
            all_words.update(c.split())
        for i in range(200):
            assert f"w{i}" in all_words


class TestDocumentChunkerPlainText:
    def test_short_text(self, chunker: DocumentChunker):
        chunks = chunker.chunk("Hello world", "test.txt")
        assert len(chunks) == 1
        assert chunks[0].text == "Hello world"
        assert chunks[0].source == "test.txt"
        assert chunks[0].chunk_index == 0

    def test_empty_text(self, chunker: DocumentChunker):
        chunks = chunker.chunk("", "test.txt")
        assert len(chunks) == 0

    def test_paragraph_split(self, chunker: DocumentChunker):
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunks = chunker.chunk(text, "test.txt", chunk_size=5)
        assert all(c.metadata["format"] == "text" for c in chunks)
        assert all(c.source == "test.txt" for c in chunks)

    def test_large_text_splits(self, chunker: DocumentChunker):
        text = " ".join(f"word{i}" for i in range(1000))
        chunks = chunker.chunk(text, "large.txt", chunk_size=50, overlap=10)
        assert len(chunks) > 1
        # All chunks have sequential indices
        for i, c in enumerate(chunks):
            assert c.chunk_index == i


class TestDocumentChunkerMarkdown:
    def test_header_split(self, chunker: DocumentChunker):
        text = "# Header 1\n\nContent one.\n\n## Header 2\n\nContent two."
        chunks = chunker.chunk(text, "readme.md")
        assert len(chunks) >= 1
        assert all(c.metadata["format"] == "markdown" for c in chunks)

    def test_large_markdown(self, chunker: DocumentChunker):
        sections = []
        for i in range(20):
            sections.append(f"## Section {i}\n\n" + " ".join(f"word{j}" for j in range(100)))
        text = "\n\n".join(sections)
        chunks = chunker.chunk(text, "big.md", chunk_size=50, overlap=10)
        assert len(chunks) > 1


class TestDocumentChunkerCode:
    def test_python_functions(self, chunker: DocumentChunker):
        text = 'def foo():\n    pass\n\ndef bar():\n    pass\n\nclass Baz:\n    pass'
        chunks = chunker.chunk(text, "app.py")
        assert all(c.metadata["format"] == "code" for c in chunks)

    def test_fallback_for_no_boundaries(self, chunker: DocumentChunker):
        text = "x = 1\ny = 2\nz = 3\n"
        chunks = chunker.chunk(text, "snippet.py")
        assert len(chunks) >= 1


class TestDocumentChunkerFile:
    def test_read_text_file(self, chunker: DocumentChunker, tmp_dir: str):
        fpath = os.path.join(tmp_dir, "test.txt")
        Path(fpath).write_text("Hello from file!", encoding="utf-8")
        chunks = chunker.chunk_file(fpath)
        assert len(chunks) == 1
        assert chunks[0].text == "Hello from file!"

    def test_unsupported_extension(self, chunker: DocumentChunker, tmp_dir: str):
        fpath = os.path.join(tmp_dir, "test.xyz")
        Path(fpath).write_text("data", encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported file type"):
            chunker.chunk_file(fpath)

    def test_file_too_large(self, chunker: DocumentChunker, tmp_dir: str):
        fpath = os.path.join(tmp_dir, "big.txt")
        Path(fpath).write_text("x", encoding="utf-8")
        with patch.object(Path, "stat") as mock_stat:
            mock_stat.return_value = MagicMock(st_size=MAX_FILE_SIZE_BYTES + 1)
            with pytest.raises(ValueError, match="File too large"):
                chunker.chunk_file(fpath)

    def test_markdown_file(self, chunker: DocumentChunker, tmp_dir: str):
        fpath = os.path.join(tmp_dir, "readme.md")
        Path(fpath).write_text("# Title\n\nContent.", encoding="utf-8")
        chunks = chunker.chunk_file(fpath)
        assert len(chunks) >= 1
        assert chunks[0].metadata["format"] == "markdown"


# ===========================================================================
# Embedding Service Tests
# ===========================================================================


class TestEmbeddingService:
    @pytest.mark.asyncio
    async def test_embed_ollama(self):
        svc = EmbeddingService(provider="ollama", model="test-model", base_url="http://localhost:11434")
        with patch.object(svc, "_call_api", new_callable=AsyncMock, return_value=[[0.1, 0.2, 0.3]]):
            vec = await svc.embed("hello")
            assert vec == [0.1, 0.2, 0.3]
        await svc.close()

    @pytest.mark.asyncio
    async def test_embed_openai(self):
        svc = EmbeddingService(provider="openai", model="text-embedding-3-small", base_url="http://localhost:1234")
        with patch.object(svc, "_call_api", new_callable=AsyncMock, return_value=[[0.4, 0.5, 0.6]]):
            vec = await svc.embed("hello")
            assert vec == [0.4, 0.5, 0.6]
        await svc.close()

    @pytest.mark.asyncio
    async def test_embed_caching(self):
        svc = EmbeddingService(provider="ollama", model="test", base_url="http://localhost:11434")
        with patch.object(svc, "_call_api", new_callable=AsyncMock, return_value=[[1.0, 2.0]]) as mock_api:
            v1 = await svc.embed("same text")
            v2 = await svc.embed("same text")
            assert v1 == v2
            assert mock_api.call_count == 1  # Second call from cache
        await svc.close()

    @pytest.mark.asyncio
    async def test_embed_batch(self):
        svc = EmbeddingService(provider="ollama", model="test", base_url="http://localhost:11434")
        with patch.object(svc, "_call_api", new_callable=AsyncMock, return_value=[[1.0], [2.0], [3.0]]):
            vecs = await svc.embed_batch(["a", "b", "c"])
            assert len(vecs) == 3
        await svc.close()

    @pytest.mark.asyncio
    async def test_unsupported_provider(self):
        svc = EmbeddingService(provider="unknown", model="m", base_url="http://localhost:1234")
        with pytest.raises(EmbeddingError, match="Unsupported"):
            await svc.embed("hello")
        await svc.close()


# ===========================================================================
# Vector Store Tests
# ===========================================================================


@_skip_no_chromadb
class TestVectorStore:
    def test_create_and_list(self, vector_store: VectorStore):
        vector_store.create_collection("test1")
        stats = vector_store.list_collections()
        names = [s.name for s in stats]
        assert "test1" in names

    def test_add_and_query(self, vector_store: VectorStore):
        vector_store.create_collection("docs")
        texts = ["the cat sat on the mat", "the dog ran in the park", "python is a programming language"]
        embeddings = [_fake_embedding(t) for t in texts]
        metadatas = [{"source": f"doc{i}.txt", "chunk_index": i} for i in range(3)]

        added = vector_store.add("docs", texts, embeddings, metadatas=metadatas)
        assert added == 3

        results = vector_store.query("docs", _fake_embedding("cat mat"), top_k=2)
        assert len(results) == 2
        assert all(isinstance(r, QueryResult) for r in results)

    def test_collection_stats(self, vector_store: VectorStore):
        vector_store.create_collection("stats_test")
        texts = ["chunk1", "chunk2"]
        embeddings = [_fake_embedding(t) for t in texts]
        vector_store.add("stats_test", texts, embeddings)

        stats = vector_store.collection_stats("stats_test")
        assert stats.name == "stats_test"
        assert stats.count == 2

    def test_delete_collection(self, vector_store: VectorStore):
        vector_store.create_collection("to_delete")
        vector_store.delete_collection("to_delete")
        names = [s.name for s in vector_store.list_collections()]
        assert "to_delete" not in names

    def test_capacity_limit(self, vector_store: VectorStore):
        vector_store.create_collection("limited")
        # Store has max_chunks_per_collection=100
        texts = [f"chunk{i}" for i in range(110)]
        embeddings = [_fake_embedding(t) for t in texts]
        added = vector_store.add("limited", texts, embeddings)
        assert added == 100  # Should cap at 100

        # Adding more should return 0
        more_texts = ["extra"]
        more_embeddings = [_fake_embedding("extra")]
        added2 = vector_store.add("limited", more_texts, more_embeddings)
        assert added2 == 0

    def test_query_empty_collection(self, vector_store: VectorStore):
        vector_store.create_collection("empty")
        results = vector_store.query("empty", _fake_embedding("anything"), top_k=5)
        assert results == []

    def test_query_nonexistent_collection(self, vector_store: VectorStore):
        with pytest.raises(VectorStoreError, match="not found"):
            vector_store.query("nonexistent", _fake_embedding("q"))

    def test_metadata_cleaning(self, vector_store: VectorStore):
        """Non str/int/float/bool metadata values are stringified."""
        vector_store.create_collection("meta_test")
        texts = ["test"]
        embeddings = [_fake_embedding("test")]
        metadatas = [{"source": "test.txt", "nested": {"a": 1}, "chunk_index": 0}]
        added = vector_store.add("meta_test", texts, embeddings, metadatas=metadatas)
        assert added == 1


# ===========================================================================
# Tool Catalog & Policy Tests
# ===========================================================================


class TestRagToolCatalog:
    def test_rag_tools_registered(self):
        for name in ("rag_ingest", "rag_query", "rag_collections"):
            assert name in TOOL_NAMES

    def test_rag_aliases(self):
        assert TOOL_NAME_ALIASES["ragingest"] == "rag_ingest"
        assert TOOL_NAME_ALIASES["ragquery"] == "rag_query"
        assert TOOL_NAME_ALIASES["rag_search"] == "rag_query"
        assert TOOL_NAME_ALIASES["ragcollections"] == "rag_collections"
        assert TOOL_NAME_ALIASES["rag_list"] == "rag_collections"


class TestRagToolPolicy:
    def test_read_only_has_query(self):
        assert "rag_query" in TOOL_PROFILES["read_only"]
        assert "rag_collections" in TOOL_PROFILES["read_only"]
        assert "rag_ingest" not in TOOL_PROFILES["read_only"]

    def test_research_has_all_rag(self):
        for name in ("rag_ingest", "rag_query", "rag_collections"):
            assert name in TOOL_PROFILES["research"]

    def test_coding_has_all_rag(self):
        for name in ("rag_ingest", "rag_query", "rag_collections"):
            assert name in TOOL_PROFILES["coding"]


# ===========================================================================
# RAG Tool Integration Tests
# ===========================================================================


@_skip_no_chromadb
class TestRagTools:
    @pytest_asyncio.fixture
    async def tooling(self, tmp_dir: str):
        from app.tools import AgentTooling
        tools = AgentTooling(workspace_root=tmp_dir)

        mock_emb = AsyncMock(spec=EmbeddingService)
        mock_emb.embed = AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8])
        mock_emb.embed_batch = AsyncMock(return_value=[[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]])

        store = VectorStore(persist_dir=os.path.join(tmp_dir, "chroma"), max_chunks_per_collection=1000)

        tools._embedding_service = mock_emb
        tools._vector_store = store
        yield tools

    @pytest.mark.asyncio
    async def test_rag_disabled(self, tmp_dir: str):
        from app.tools import AgentTooling, ToolExecutionError
        tools = AgentTooling(workspace_root=tmp_dir)
        with patch.object(settings, "rag_enabled", False):
            with pytest.raises(ToolExecutionError, match="RAG is disabled"):
                await tools.rag_ingest("test.txt")

    @pytest.mark.asyncio
    async def test_rag_ingest_file(self, tooling, tmp_dir: str):
        fpath = os.path.join(tmp_dir, "doc.txt")
        Path(fpath).write_text("This is a test document with some content.", encoding="utf-8")
        with patch.object(settings, "rag_enabled", True):
            result = await tooling.rag_ingest("doc.txt", collection="test_col")
        assert "Ingested" in result
        assert "test_col" in result

    @pytest.mark.asyncio
    async def test_rag_ingest_missing_file(self, tooling, tmp_dir: str):
        from app.tools import ToolExecutionError
        with patch.object(settings, "rag_enabled", True):
            with pytest.raises(ToolExecutionError, match="File not found"):
                await tooling.rag_ingest("nonexistent.txt")

    @pytest.mark.asyncio
    async def test_rag_query(self, tooling, tmp_dir: str):
        # First ingest
        fpath = os.path.join(tmp_dir, "doc.txt")
        Path(fpath).write_text("Python is a great programming language.", encoding="utf-8")
        with patch.object(settings, "rag_enabled", True):
            await tooling.rag_ingest("doc.txt", collection="query_col")

        with patch.object(settings, "rag_enabled", True), \
             patch.object(settings, "rag_default_top_k", 5):
            result = await tooling.rag_query("What is Python?", collection="query_col")
        assert "score:" in result

    @pytest.mark.asyncio
    async def test_rag_query_empty_collection(self, tooling, tmp_dir: str):
        tooling._vector_store.create_collection("empty_col")
        with patch.object(settings, "rag_enabled", True), \
             patch.object(settings, "rag_default_top_k", 5):
            result = await tooling.rag_query("anything", collection="empty_col")
        assert "No results" in result

    @pytest.mark.asyncio
    async def test_rag_collections_empty(self, tooling, tmp_dir: str):
        with patch.object(settings, "rag_enabled", True):
            result = tooling.rag_collections()
        assert "No collections" in result

    @pytest.mark.asyncio
    async def test_rag_collections_with_data(self, tooling, tmp_dir: str):
        fpath = os.path.join(tmp_dir, "doc.txt")
        Path(fpath).write_text("Some content here.", encoding="utf-8")
        with patch.object(settings, "rag_enabled", True):
            await tooling.rag_ingest("doc.txt", collection="col1")
            result = tooling.rag_collections()
        assert "col1" in result
        assert "chunks" in result


# ===========================================================================
# Config Tests
# ===========================================================================


class TestRagConfig:
    def test_defaults(self):
        assert isinstance(settings.rag_enabled, bool)
        assert settings.rag_embedding_provider in ("ollama", "openai")
        assert settings.rag_default_top_k >= 1
        assert settings.rag_max_chunks_per_collection >= 100
