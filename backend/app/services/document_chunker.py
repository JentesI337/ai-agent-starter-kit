"""Document chunking with format-aware splitting strategies.

Splits documents into overlapping chunks suitable for embedding and
vector search.  Supports Markdown, code, plain text, and PDF (optional).
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("app.services.document_chunker")

# Supported file extensions for RAG ingestion
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".md", ".txt", ".py", ".js", ".ts", ".json", ".csv", ".html", ".pdf",
     ".jsx", ".tsx", ".java", ".go", ".rs", ".c", ".cpp", ".h", ".rb", ".yml", ".yaml"}
)

# Max file size for ingestion (10 MB)
MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024


@dataclass
class Chunk:
    """A text chunk from a document."""
    text: str
    source: str
    chunk_index: int
    page: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _approx_token_count(text: str) -> int:
    """Approximate token count using word count × 1.3."""
    return int(len(text.split()) * 1.3)


def _split_by_tokens(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text into chunks of approximately `chunk_size` tokens with overlap."""
    words = text.split()
    if not words:
        return []

    # Approximate tokens per word: ~1.3
    words_per_chunk = max(1, int(chunk_size / 1.3))
    words_overlap = max(0, int(overlap / 1.3))

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + words_per_chunk, len(words))
        chunk_text = " ".join(words[start:end])
        if chunk_text.strip():
            chunks.append(chunk_text)
        if end >= len(words):
            break
        start = end - words_overlap
        if start <= (end - words_per_chunk):  # Prevent infinite loop
            start = end
    return chunks


class DocumentChunker:
    """Split documents into chunks for embedding."""

    def chunk(
        self,
        text: str,
        source: str,
        *,
        chunk_size: int = 512,
        overlap: int = 64,
    ) -> list[Chunk]:
        """Chunk a text string based on its inferred type."""
        ext = os.path.splitext(source)[1].lower() if source else ""
        if ext == ".md":
            return self._chunk_markdown(text, source, chunk_size, overlap)
        elif ext in (".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
                      ".c", ".cpp", ".h", ".rb"):
            return self._chunk_code(text, source, chunk_size, overlap)
        else:
            return self._chunk_plain(text, source, chunk_size, overlap)

    def chunk_file(
        self,
        path: str,
        *,
        chunk_size: int = 512,
        overlap: int = 64,
    ) -> list[Chunk]:
        """Read a file and chunk it. Supports text files and PDF (optional)."""
        file_path = Path(path)
        ext = file_path.suffix.lower()

        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {ext}")

        size = file_path.stat().st_size
        if size > MAX_FILE_SIZE_BYTES:
            raise ValueError(f"File too large for ingestion: {size} bytes (max {MAX_FILE_SIZE_BYTES})")

        if ext == ".pdf":
            return self._chunk_pdf(str(file_path), chunk_size, overlap)

        text = file_path.read_text(encoding="utf-8", errors="replace")
        return self.chunk(text, str(file_path), chunk_size=chunk_size, overlap=overlap)

    # ------------------------------------------------------------------
    # Markdown chunking
    # ------------------------------------------------------------------

    def _chunk_markdown(
        self, text: str, source: str, chunk_size: int, overlap: int
    ) -> list[Chunk]:
        """Split markdown by headers, then by token count."""
        # Split at ## or ### headers
        sections = re.split(r"(?m)^(#{1,3}\s+.+)$", text)

        # Reassemble: pair each header with its following content
        merged_sections: list[str] = []
        current = ""
        for part in sections:
            if re.match(r"^#{1,3}\s+", part):
                if current.strip():
                    merged_sections.append(current.strip())
                current = part + "\n"
            else:
                current += part
        if current.strip():
            merged_sections.append(current.strip())

        chunks: list[Chunk] = []
        idx = 0
        for section in merged_sections:
            if _approx_token_count(section) <= chunk_size:
                if section.strip():
                    chunks.append(Chunk(
                        text=section.strip(),
                        source=source,
                        chunk_index=idx,
                        metadata={"format": "markdown"},
                    ))
                    idx += 1
            else:
                sub_chunks = _split_by_tokens(section, chunk_size, overlap)
                for sub in sub_chunks:
                    chunks.append(Chunk(
                        text=sub.strip(),
                        source=source,
                        chunk_index=idx,
                        metadata={"format": "markdown"},
                    ))
                    idx += 1
        return chunks

    # ------------------------------------------------------------------
    # Code chunking
    # ------------------------------------------------------------------

    def _chunk_code(
        self, text: str, source: str, chunk_size: int, overlap: int
    ) -> list[Chunk]:
        """Split code at function/class boundaries, fallback to token split."""
        # Try to split at function/class boundaries
        pattern = r"^(?:def |class |function |async function |export |public |private |const |let |var |func )"
        parts = re.split(f"(?={pattern})", text, flags=re.MULTILINE)

        if len(parts) <= 1:
            # Fallback: token-based split
            return self._chunk_plain(text, source, chunk_size, overlap)

        chunks: list[Chunk] = []
        idx = 0
        current = ""
        for part in parts:
            combined = (current + "\n" + part).strip() if current else part.strip()
            if _approx_token_count(combined) <= chunk_size:
                current = combined
            else:
                if current.strip():
                    chunks.append(Chunk(
                        text=current.strip(),
                        source=source,
                        chunk_index=idx,
                        metadata={"format": "code"},
                    ))
                    idx += 1
                if _approx_token_count(part) > chunk_size:
                    sub_chunks = _split_by_tokens(part, chunk_size, overlap)
                    for sub in sub_chunks:
                        chunks.append(Chunk(
                            text=sub.strip(),
                            source=source,
                            chunk_index=idx,
                            metadata={"format": "code"},
                        ))
                        idx += 1
                    current = ""
                else:
                    current = part.strip()

        if current.strip():
            chunks.append(Chunk(
                text=current.strip(),
                source=source,
                chunk_index=idx,
                metadata={"format": "code"},
            ))

        return chunks

    # ------------------------------------------------------------------
    # Plain text chunking
    # ------------------------------------------------------------------

    def _chunk_plain(
        self, text: str, source: str, chunk_size: int, overlap: int
    ) -> list[Chunk]:
        """Split plain text by paragraphs, then by tokens."""
        paragraphs = re.split(r"\n\s*\n", text)

        chunks: list[Chunk] = []
        idx = 0
        current = ""
        for para in paragraphs:
            combined = (current + "\n\n" + para).strip() if current else para.strip()
            if _approx_token_count(combined) <= chunk_size:
                current = combined
            else:
                if current.strip():
                    chunks.append(Chunk(
                        text=current.strip(),
                        source=source,
                        chunk_index=idx,
                        metadata={"format": "text"},
                    ))
                    idx += 1
                if _approx_token_count(para) > chunk_size:
                    sub_chunks = _split_by_tokens(para, chunk_size, overlap)
                    for sub in sub_chunks:
                        chunks.append(Chunk(
                            text=sub.strip(),
                            source=source,
                            chunk_index=idx,
                            metadata={"format": "text"},
                        ))
                        idx += 1
                    current = ""
                else:
                    current = para.strip()

        if current.strip():
            chunks.append(Chunk(
                text=current.strip(),
                source=source,
                chunk_index=idx,
                metadata={"format": "text"},
            ))

        return [c for c in chunks if c.text.strip()]

    # ------------------------------------------------------------------
    # PDF chunking (optional dependency)
    # ------------------------------------------------------------------

    def _chunk_pdf(
        self, path: str, chunk_size: int, overlap: int
    ) -> list[Chunk]:
        """Chunk a PDF file page-by-page, then by tokens."""
        try:
            import fitz  # type: ignore[import-untyped]  # pymupdf
        except ImportError:
            raise RuntimeError(
                "PDF ingestion requires pymupdf. Install with: pip install pymupdf"
            )

        doc = fitz.open(path)
        chunks: list[Chunk] = []
        idx = 0

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            if not text.strip():
                continue

            if _approx_token_count(text) <= chunk_size:
                chunks.append(Chunk(
                    text=text.strip(),
                    source=path,
                    chunk_index=idx,
                    page=page_num + 1,
                    metadata={"format": "pdf"},
                ))
                idx += 1
            else:
                sub_chunks = _split_by_tokens(text, chunk_size, overlap)
                for sub in sub_chunks:
                    chunks.append(Chunk(
                        text=sub.strip(),
                        source=path,
                        chunk_index=idx,
                        page=page_num + 1,
                        metadata={"format": "pdf"},
                    ))
                    idx += 1

        doc.close()
        return [c for c in chunks if c.text.strip()]
