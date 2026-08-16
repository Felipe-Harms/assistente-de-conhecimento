-- =============================================================================
-- Upwork Knowledge Assistant — initial schema
-- =============================================================================
-- This file is mounted under /docker-entrypoint-initdb.d by the pgvector image.
-- It is only executed on the first boot of a fresh volume; subsequent boots
-- skip it. The runtime `api.app.db.ensure_schema()` applies the same DDL
-- (CREATE/ADD COLUMN IF NOT EXISTS) so live migrations are idempotent.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- Source documents. One row per ingested file.
CREATE TABLE IF NOT EXISTS documents (
    id           BIGSERIAL PRIMARY KEY,
    workspace    TEXT NOT NULL DEFAULT 'default',
    source       TEXT NOT NULL,
    -- 'markdown' | 'text' | 'pdf' (REQ-002 surface)
    mime_type    TEXT NOT NULL,
    -- Original filename + size for traceability.
    file_name    TEXT NOT NULL,
    byte_size    BIGINT NOT NULL,
    content_sha  TEXT NOT NULL,
    metadata     JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace, content_sha)
);

-- Chunks produced by the splitter. Embedding column is added dynamically by
-- `api.app.db.ensure_schema` once EMBEDDING_DIM is finalised; we keep the
-- table shape minimal here so the schema can flex with the runtime dim.
CREATE TABLE IF NOT EXISTS chunks (
    id           BIGSERIAL PRIMARY KEY,
    document_id  BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    workspace    TEXT NOT NULL DEFAULT 'default',
    ordinal      INT NOT NULL,
    content      TEXT NOT NULL,
    content_sha  TEXT NOT NULL,
    page         INT,
    section      TEXT,
    char_start   INT,
    char_end     INT,
    metadata     JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS chunks_workspace_idx ON chunks(workspace);
CREATE INDEX IF NOT EXISTS chunks_document_idx ON chunks(document_id);

-- Collections — (REQ-002/REQ-003). A collection is a named bucket
-- of documents within a workspace; queries are scoped to a collection so
-- two collections in the same workspace are isolated.
CREATE TABLE IF NOT EXISTS collections (
    id           BIGSERIAL PRIMARY KEY,
    workspace    TEXT NOT NULL DEFAULT 'default',
    name         TEXT NOT NULL,
    description  TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace, name)
);

-- Chat history (REQ-004 / REQ-006). Empty skeleton; real fields in a later phase.
CREATE TABLE IF NOT EXISTS chat_messages (
    id           BIGSERIAL PRIMARY KEY,
    workspace    TEXT NOT NULL DEFAULT 'default',
    session_id   TEXT NOT NULL,
    role         TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content      TEXT NOT NULL,
    citations    JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS chat_messages_session_idx ON chat_messages(session_id, created_at);

-- Audit trail mirror (canonical store is stdout JSON from the API; this table
-- is an optional structured mirror activated when RETENTION_DAYS > 0).
CREATE TABLE IF NOT EXISTS audit_events (
    id           BIGSERIAL PRIMARY KEY,
    request_id   TEXT,
    principal    TEXT,
    method       TEXT,
    path         TEXT,
    status       INT,
    payload      JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS audit_events_created_at_idx ON audit_events(created_at);
