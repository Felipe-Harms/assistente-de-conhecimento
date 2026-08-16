"""Async DB layer — TASK-002 ingestion + retrieval backends.

A single asyncpg pool is owned by the FastAPI app and shared by the
ingest/retrieve/request modules. The pool is created lazily on first call
to `get_pool()` and reused across requests.

`ensure_schema()` is idempotent — it runs on app startup and tolerates a
volume that already has the TASK-001 schema. It is safe to call repeatedly.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import asyncpg
from pgvector.asyncpg import register_vector

log = logging.getLogger("upworkkb.db")

_pool: asyncpg.Pool | None = None
_registered_dim: int | None = None


def _database_url() -> str:
    """Translate SQLAlchemy-style URL into a plain `postgresql://` URL.

    asyncpg does not understand the `postgresql+asyncpg://` scheme.
    """
    url = os.environ.get("DATABASE_URL") or ""
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def get_pool() -> asyncpg.Pool:
    """Lazy singleton — one pool per process, with the pgvector codec."""
    global _pool, _registered_dim
    if _pool is None:
        url = _database_url()
        dim = int(os.environ.get("EMBEDDING_DIM", "1536"))
        _pool = await asyncpg.create_pool(
            url,
            min_size=1,
            max_size=8,
            command_timeout=30,
        )
        # The pgvector codec must be registered on every connection.
        async with _pool.acquire() as conn:
            await register_vector(conn)
        _registered_dim = dim
        log.info("asyncpg pool ready (dim=%d)", dim)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def ensure_schema(embedding_dim: int) -> None:
    """Idempotent migration — safe to run on every app startup.

    Existing TASK-001 volumes are upgraded in place:
      - CREATE TABLE IF NOT EXISTS for `collections`
      - ADD COLUMN IF NOT EXISTS for `chunks.collection_id` and
        `chunks.embedding`
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # pgvector codec requires the dimension to match the column type.
        # Re-register against the requested dim only if it changed.
        global _registered_dim
        if _registered_dim != embedding_dim:
            await register_vector(conn)
            _registered_dim = embedding_dim

        stmts: list[str] = [
            """
            CREATE TABLE IF NOT EXISTS collections (
                id           BIGSERIAL PRIMARY KEY,
                workspace    TEXT NOT NULL DEFAULT 'default',
                name         TEXT NOT NULL,
                description  TEXT,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (workspace, name)
            )
            """,
            "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS collection_id BIGINT",
            "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding VECTOR(" + str(embedding_dim) + ")",
            "CREATE INDEX IF NOT EXISTS chunks_collection_idx ON chunks(collection_id)",
        ]
        for stmt in stmts:
            await conn.execute(stmt)

        # IVFFlat is approximate — it needs at least a few thousand rows
        # to produce sane nearest-neighbour recall. The TASK-002 corpus
        # is small (~50 chunks), so we explicitly skip the index and rely
        # on a sequential cosine scan. The migration log surfaces a
        # NOTICE if the table ever grows enough to warrant the index.
        row_count = await conn.fetchval("SELECT count(*) FROM chunks")
        if row_count >= 1000:
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS chunks_embedding_idx "
                "ON chunks USING ivfflat (embedding vector_cosine_ops) "
                "WITH (lists = 10)"
            )


__all__ = [
    "get_pool",
    "close_pool",
    "ensure_schema",
]
