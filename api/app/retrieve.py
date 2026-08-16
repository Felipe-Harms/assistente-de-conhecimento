"""Retrieval pipeline — REQ-003 + REQ-004.

Queries a collection using cosine similarity over pgvector. Returns the
top-k chunks with their scores, normalised to [0, 1] (1.0 = identical).

The retrieval ranker is deliberately binary: either the top score clears
the configured threshold (caller in `api.app.generate` formats an answer)
or the request is refused with `insufficient_evidence`. No fabrication
is permitted — REQ-004 is non-negotiable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import asyncpg
from pgvector.asyncpg import register_vector

from app.embeddings import EmbeddingClient

log = logging.getLogger("upworkkb.retrieve")


@dataclass
class Citation:
    chunk_id: int
    document_id: int
    source: str
    file_name: str
    page: int | None
    section: str | None
    score: float
    text: str

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "source_id": self.source,
            "file_name": self.file_name,
            "page": self.page,
            "section": self.section,
            "score": round(self.score, 4),
            "text": self.text,
        }


@dataclass
class RetrievalResult:
    chunks: list[Citation]
    best_score: float

    @property
    def supported(self) -> bool:
        return self.best_score >= self.threshold if self.chunks else False

    @property
    def threshold(self) -> float:
        return _LAST_THRESHOLD


_LAST_THRESHOLD = 0.35


async def query(
    *,
    pool: asyncpg.Pool,
    embedder: EmbeddingClient,
    question: str,
    collection_id: int,
    workspace: str,
    top_k: int = 5,
    threshold: float = 0.35,
) -> RetrievalResult:
    """Return top-k citations for `question` inside `collection_id`.

    On no hits or empty collection, returns an empty result with
    `best_score = 0.0`. The caller decides whether to answer or refuse.
    """
    global _LAST_THRESHOLD
    _LAST_THRESHOLD = threshold

    async with pool.acquire() as conn:
        await register_vector(conn)

    vectors = await embedder.embed([question])
    query_vec = vectors[0]

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                c.id            AS chunk_id,
                c.document_id   AS document_id,
                c.content       AS content,
                c.page          AS page,
                c.section       AS section,
                c.content_sha   AS chunk_sha,
                d.source        AS source,
                d.file_name     AS file_name,
                d.content_sha   AS doc_sha,
                1 - (c.embedding <=> $1::vector) AS score
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.collection_id = $2
              AND c.workspace = $3
            ORDER BY c.embedding <=> $1::vector
            LIMIT $4
            """,
            query_vec,
            collection_id,
            workspace,
            top_k,
        )

    if not rows:
        return RetrievalResult(chunks=[], best_score=0.0)

    citations = [
        Citation(
            chunk_id=r["chunk_id"],
            document_id=r["document_id"],
            source=r["source"],
            file_name=r["file_name"],
            page=r["page"],
            section=r["section"],
            score=float(r["score"]),
            text=r["content"],
        )
        for r in rows
    ]
    return RetrievalResult(chunks=citations, best_score=citations[0].score)


__all__ = ["Citation", "RetrievalResult", "query"]
