"""Ingestion pipeline — TASK-002 / REQ-002.

Responsibilities:
  - Accept files (bytes), a path, or inline text.
  - Validate format (markdown / text / pdf) and size.
  - Split into chunks (~512 tokens / 64 tokens overlap).
  - Hash content (SHA-256).
  - Embed each chunk using the configured embedding client.
  - Persist documents + chunks + embeddings into pgvector.

PDFs are parsed textually with pypdf. Scanned PDFs (no extractable text)
are rejected with a clear error — the project explicitly excludes OCR.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import asyncpg
from pgvector.asyncpg import register_vector

from app.embeddings import EmbeddingClient

log = logging.getLogger("upworkkb.ingest")


# ---------------------------------------------------------------------------
# Format detection + size guard
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = {".md", ".markdown", ".txt", ".pdf"}
MAX_INLINE_TEXT_CHARS = 200_000


class IngestError(ValueError):
    """Raised on any user-facing validation failure (4xx surface)."""


def _detect_format(file_name: str, declared_mime: str | None = None) -> str:
    """Return one of `markdown` | `text` | `pdf` or raise IngestError."""
    ext = Path(file_name).suffix.lower()
    if ext in {".md", ".markdown"}:
        return "markdown"
    if ext == ".txt":
        return "text"
    if ext == ".pdf":
        return "pdf"
    raise IngestError(f"unsupported file extension: {ext!r}")


def _enforce_size(byte_size: int, max_bytes: int) -> None:
    if byte_size <= 0:
        raise IngestError("file is empty")
    if byte_size > max_bytes:
        raise IngestError(
            f"file too large: {byte_size} bytes > max {max_bytes} bytes"
        )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

@dataclass
class Section:
    """A logical chunk of a document — one markdown section, one PDF page,
    or one text block. The pipeline treats sections as the natural
    pre-chunk boundary so we never split mid-paragraph when avoidable.
    """

    content: str
    page: int | None = None
    section: str | None = None


def _parse_markdown(text: str) -> list[Section]:
    """Split on H1/H2/H3 headings; each section keeps its heading text."""
    sections: list[Section] = []
    lines = text.splitlines()
    current_heading = "preamble"
    current_lines: list[str] = []
    for line in lines:
        stripped = line.rstrip()
        if re.match(r"^#{1,3}\s+", stripped):
            if current_lines:
                sections.append(
                    Section(
                        content="\n".join(current_lines).strip(),
                        section=current_heading,
                    )
                )
            current_heading = stripped.lstrip("#").strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append(
            Section(content="\n".join(current_lines).strip(), section=current_heading)
        )
    # Drop empty sections (pure whitespace).
    return [s for s in sections if s.content]


def _parse_text(text: str) -> list[Section]:
    """Plain text — one section per non-empty paragraph block."""
    blocks = re.split(r"\n\s*\n", text)
    return [
        Section(content=b.strip(), section="paragraph")
        for b in blocks
        if b.strip()
    ]


def _parse_pdf(data: bytes) -> list[Section]:
    """Extract text page by page. Reject scanned PDFs (no text)."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    sections: list[Section] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # pragma: no cover — defensive
            raise IngestError(f"pdf page {i} extraction failed: {exc}") from exc
        text = text.strip()
        if not text:
            # No text means either a scanned page or an image-only PDF.
            # The contract explicitly excludes OCR.
            raise IngestError(
                f"pdf page {i} has no extractable text (scanned PDF / OCR not supported)"
            )
        sections.append(Section(content=text, page=i, section=f"page {i}"))
    if not sections:
        raise IngestError("pdf has no extractable text")
    return sections


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _split_into_chunks(
    sections: Iterable[Section],
    *,
    chunk_size: int,
    overlap: int,
) -> list[dict]:
    """Word-boundary aware sliding window. Honors section boundaries when
    a section fits inside a chunk; otherwise splits mid-section but always
    at a word boundary.

    Returns a list of plain dicts ready for DB insertion.
    """
    chunks: list[dict] = []
    ordinal = 0
    for sec in sections:
        text = sec.content
        if not text:
            continue
        if len(text) <= chunk_size:
            chunks.append(
                {
                    "ordinal": ordinal,
                    "content": text,
                    "page": sec.page,
                    "section": sec.section,
                    "char_start": 0,
                    "char_end": len(text),
                }
            )
            ordinal += 1
            continue
        # Multi-chunk: slide a window of `chunk_size` with `overlap` overlap.
        start = 0
        n = len(text)
        while start < n:
            end = min(start + chunk_size, n)
            # Walk back to a word boundary (and forward if we hit end).
            if end < n:
                ws = text.rfind(" ", start, end)
                if ws > start + chunk_size // 2:
                    end = ws
            piece = text[start:end].strip()
            if piece:
                chunks.append(
                    {
                        "ordinal": ordinal,
                        "content": piece,
                        "page": sec.page,
                        "section": sec.section,
                        "char_start": start,
                        "char_end": end,
                    }
                )
                ordinal += 1
            if end >= n:
                break
            start = max(end - overlap, start + 1)
    return chunks


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class IngestResult:
    document_id: int
    collection_id: int
    chunks_created: int
    content_sha: str
    chunk_hashes: list[str]


async def ingest_bytes(
    *,
    pool: asyncpg.Pool,
    embedder: EmbeddingClient,
    data: bytes,
    file_name: str,
    workspace: str,
    collection_name: str,
    declared_mime: str | None = None,
    max_bytes: int = 10 * 1024 * 1024,
    chunk_size: int = 2000,
    chunk_overlap: int = 256,
) -> IngestResult:
    """Validate, parse, chunk, embed, and persist a single file.

    Returns the document id, the resolved collection id, the number of
    chunks created, and the SHA-256 of the file content.
    """
    # pgvector codec must be registered before we touch `embedding` columns.
    async with pool.acquire() as _conn:
        await register_vector(_conn)

    _enforce_size(len(data), max_bytes)
    fmt = _detect_format(file_name, declared_mime)

    if fmt == "markdown":
        text = data.decode("utf-8", errors="replace")
        sections = _parse_markdown(text)
    elif fmt == "text":
        text = data.decode("utf-8", errors="replace")
        sections = _parse_text(text)
    elif fmt == "pdf":
        sections = _parse_pdf(data)
    else:  # pragma: no cover — defensive
        raise IngestError(f"unsupported format: {fmt}")

    if not sections:
        raise IngestError("document has no extractable content")

    raw_chunks = _split_into_chunks(
        sections, chunk_size=chunk_size, overlap=chunk_overlap
    )
    if not raw_chunks:
        raise IngestError("chunker produced no chunks")

    content_sha = sha256_bytes(data)
    mime_type = {
        "markdown": "text/markdown",
        "text": "text/plain",
        "pdf": "application/pdf",
    }[fmt]

    # Collection resolution — create-or-get by (workspace, name).
    async with pool.acquire() as conn:
        collection_id = await conn.fetchval(
            """
            INSERT INTO collections (workspace, name)
            VALUES ($1, $2)
            ON CONFLICT (workspace, name) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            workspace,
            collection_name,
        )

        # Document upsert by (workspace, content_sha) — same content,
        # same workspace ⇒ reuse the existing document id.
        doc_row = await conn.fetchrow(
            """
            INSERT INTO documents (workspace, source, mime_type, file_name,
                                   byte_size, content_sha, metadata)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
            ON CONFLICT (workspace, content_sha) DO UPDATE
              SET file_name = EXCLUDED.file_name
            RETURNING id
            """,
            workspace,
            file_name,
            mime_type,
            file_name,
            len(data),
            content_sha,
            '{"format": "' + fmt + '"}',
        )
        document_id = doc_row["id"]

    # Embed chunks (possibly in batches if the doc is huge).
    chunk_texts = [c["content"] for c in raw_chunks]
    vectors = await embedder.embed(chunk_texts)

    chunk_hashes: list[str] = []
    async with pool.acquire() as conn:
        # Replace chunks for this document — idempotent re-ingest.
        await conn.execute("DELETE FROM chunks WHERE document_id = $1", document_id)
        for raw, vec in zip(raw_chunks, vectors):
            chunk_hash = sha256_text(raw["content"])
            chunk_hashes.append(chunk_hash)
            await conn.execute(
                """
                INSERT INTO chunks (
                    document_id, workspace, collection_id, ordinal, content,
                    content_sha, page, section, char_start, char_end, embedding
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                document_id,
                workspace,
                collection_id,
                raw["ordinal"],
                raw["content"],
                chunk_hash,
                raw["page"],
                raw["section"],
                raw["char_start"],
                raw["char_end"],
                vec,
            )

    return IngestResult(
        document_id=document_id,
        collection_id=collection_id,
        chunks_created=len(raw_chunks),
        content_sha=content_sha,
        chunk_hashes=chunk_hashes,
    )


async def ingest_text(
    *,
    pool: asyncpg.Pool,
    embedder: EmbeddingClient,
    text: str,
    workspace: str,
    collection_name: str,
    source_label: str,
    max_bytes: int = 10 * 1024 * 1024,
    chunk_size: int = 2000,
    chunk_overlap: int = 256,
) -> IngestResult:
    """Inline-text convenience. Stores the text as markdown by default."""
    if len(text) > MAX_INLINE_TEXT_CHARS:
        raise IngestError(
            f"inline text too long: {len(text)} chars > {MAX_INLINE_TEXT_CHARS}"
        )
    data = text.encode("utf-8")
    # Force a `.md` extension so format detection picks markdown.
    if not source_label.endswith(".md"):
        source_label = source_label + ".md"
    return await ingest_bytes(
        pool=pool,
        embedder=embedder,
        data=data,
        file_name=source_label,
        workspace=workspace,
        collection_name=collection_name,
        max_bytes=max_bytes,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


__all__ = [
    "IngestError",
    "IngestResult",
    "SUPPORTED_EXTENSIONS",
    "ingest_bytes",
    "ingest_text",
    "sha256_bytes",
    "sha256_text",
]
