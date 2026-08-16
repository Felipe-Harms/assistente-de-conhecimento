"""FastAPI application entry point.

TASK-001 surface area:
  - `/healthz`   liveness probe (always returns 200; no DB access)
  - `/readyz`    readiness probe (returns 200 with components map)
  - `/v1/`       versioned router (embeddings stub)
  - `/`          tiny metadata JSON so the root is not a 404

TASK-002 surface area (REQ-002 / REQ-003 / REQ-004):
  - `POST /v1/collections`        create collection
  - `GET  /v1/collections`        list collections
  - `GET  /v1/collections/{id}`   details + counts
  - `POST /v1/ingest`             ingest inline text (JSON) or a file (multipart)
  - `POST /v1/query`              answer or refuse — REQ-004 non-negotiable
  - `GET  /v1/citations/{chunk_id}` trace a chunk back to its source

Auth and audit are wired at the app-level. The audit logger is a thin
fire-and-forget emitter that does not raise into the request path.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse

from app import __version__
from app.audit import (
    AuditEvent,
    AuditLogger,
    make_audit_logger,
    now_ms,
    scrub,
    timed_ms,
)
from app.auth import AuthResult, check_bearer
from app.db import close_pool, ensure_schema, get_pool
from app.embeddings import EmbeddingClient, make_client
from app.generate import REFUSAL_REASON, format_answer
from app.ingest import IngestError, ingest_bytes, ingest_text
from app.models import (
    ChunkDetail,
    CollectionCreate,
    CollectionInfo,
    EmbeddingRequest,
    EmbeddingResponse,
    HealthResponse,
    IdentityResponse,
    IngestRequest,
    IngestResponse,
    QueryRequest,
    QueryResponse,
    ReadyResponse,
)
from app.retrieve import query as retrieve_query
from app.settings import Settings

log = logging.getLogger("upworkkb.api")


# Conservative CSS color guard. Anything that does not look like a CSS
# color literal is dropped and replaced with the default accent. This is
# NOT a substitute for content-security-policy on the UI side — it is a
# cheap line of defence that keeps the JSON contract honest.
import re as _re

_ACCENT_RE = _re.compile(
    r"^(?:#[0-9a-fA-F]{3,8}|rgb\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\)|"
    r"rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*(?:0|1|0?\.\d+)\s*\))$"
)
_DEFAULT_ACCENT = "#0284c7"


def _safe_accent(value: str) -> str:
    """Return *value* if it parses as a CSS color; otherwise the default."""
    if isinstance(value, str) and _ACCENT_RE.match(value.strip()):
        return value.strip()
    return _DEFAULT_ACCENT


async def _pool(request: Request) -> "asyncpg.Pool":
    """Resolve the asyncpg pool from the module singleton.

    Tests reset the module singleton between cases; routes always read
    the live pool from `db.get_pool()` rather than caching it on
    `app.state`, so the in-process TestClient flow keeps working.
    """
    pool = await get_pool()
    request.app.state.pool = pool
    request.app.state.db_ready = True
    return pool


def _build_app(settings: Settings | None = None) -> FastAPI:
    """Pure factory — test fixtures instantiate without side effects."""

    settings = settings or Settings()  # type: ignore[call-arg]
    audit: AuditLogger = make_audit_logger()
    embedder: EmbeddingClient = make_client(
        stub=settings.embedding_stub,
        dim=settings.embedding_dim,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.audit = audit
        app.state.embedder = embedder
        app.state.db_ready = False
        # The DB pool is created lazily inside the request handlers via
        # `get_pool()` so the in-process TestClient (`tests/conftest.py`)
        # can reset the module-level singleton between tests without the
        # lifespan holding onto a closed pool. The first /v1/* request
        # warms the pool transparently; if it fails, the route returns
        # 503 until the dependency becomes reachable.
        try:
            yield
        finally:
            try:
                await embedder.close()
            except Exception:  # pragma: no cover
                pass

    app = FastAPI(
        title="Upwork Knowledge Assistant",
        version=__version__,
        lifespan=lifespan,
        # Lock the OpenAPI/docs off behind the same gate as the rest of /v1.
        docs_url="/docs" if not settings.auth_enabled else None,
        redoc_url="/redoc" if not settings.auth_enabled else None,
        openapi_url="/openapi.json" if not settings.auth_enabled else None,
    )

    @app.middleware("http")
    async def audit_and_auth(request: Request, call_next):
        start = now_ms()
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        auth_header = request.headers.get("authorization")

        auth: AuthResult = check_bearer(
            enabled=request.app.state.settings.auth_enabled,
            expected_token=request.app.state.settings.auth_token,
            presented_header=auth_header,
            request_path=request.url.path,
        )

        if not auth.allowed:
            body = JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": {"code": "unauthorized", "message": auth.reason}},
            )
            audit.emit(
                AuditEvent(
                    timestamp_ms=now_ms(),
                    request_id=rid,
                    principal=None,
                    method=request.method,
                    path=scrub(request.url.path),
                    status=401,
                    latency_ms=timed_ms(start),
                    message=f"denied: {auth.reason}",
                )
            )
            return body

        try:
            response: Response = await call_next(request)
        except HTTPException as exc:
            audit.emit(
                AuditEvent(
                    timestamp_ms=now_ms(),
                    request_id=rid,
                    principal=auth.principal,
                    method=request.method,
                    path=scrub(request.url.path),
                    status=exc.status_code,
                    latency_ms=timed_ms(start),
                    message=scrub(getattr(exc, "detail", "")) or "",
                )
            )
            raise
        except Exception as exc:  # pragma: no cover — safety net
            log.exception("unhandled error: %s", exc)
            audit.emit(
                AuditEvent(
                    timestamp_ms=now_ms(),
                    request_id=rid,
                    principal=auth.principal,
                    method=request.method,
                    path=scrub(request.url.path),
                    status=500,
                    latency_ms=timed_ms(start),
                    message=f"error: {scrub(str(exc))}",
                )
            )
            return JSONResponse(
                status_code=500,
                content={"error": {"code": "internal", "message": "internal error"}},
            )

        response.headers["x-request-id"] = rid
        audit.emit(
            AuditEvent(
                timestamp_ms=now_ms(),
                request_id=rid,
                principal=auth.principal,
                method=request.method,
                path=scrub(request.url.path),
                status=response.status_code,
                latency_ms=timed_ms(start),
                extra={"ua": scrub(request.headers.get("user-agent", "") or "")},
            )
        )
        return response

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"service": "upworkkb-api", "version": __version__}

    @app.get("/healthz", response_model=HealthResponse, tags=["meta"])
    async def healthz() -> HealthResponse:
        return HealthResponse(
            version=__version__,
            auth_enabled=settings.auth_enabled,
        )

    @app.get(
        "/v1/identity",
        response_model=IdentityResponse,
        tags=["meta"],
    )
    async def identity() -> IdentityResponse:
        """Public brand surface (REQ-006).

        Always reachable without a Bearer token so the static UI can
        render its own brand before the user has authenticated. The
        `accent_color` is validated server-side; bad input falls back
        to the default accent so the UI never gets an unsafe string.
        """
        return IdentityResponse(
            brand_name=settings.app_brand_name,
            tagline=settings.app_tagline,
            accent_color=_safe_accent(settings.app_accent_color),
            logo_url=settings.app_logo_url.strip() or "",
            footer_note=settings.app_footer_note,
            auth_enabled=settings.auth_enabled,
            version=__version__,
        )

    @app.get("/readyz", response_model=ReadyResponse, tags=["meta"])
    async def readyz(request: Request) -> ReadyResponse:
        # Lazy DB init — runs on first readiness probe, then cached.
        if not getattr(request.app.state, "db_ready", False):
            try:
                await ensure_schema(request.app.state.settings.embedding_dim)
                request.app.state.db_ready = True
            except Exception as exc:  # pragma: no cover — defensive
                log.exception("db init failed: %s", exc)
        components = {
            "config": "ok",
            "embedder": "ok",
            "db": "ok" if getattr(request.app.state, "db_ready", False) else "down",
        }
        ok = components["db"] == "ok"
        return ReadyResponse(status="ok" if ok else "degraded", components=components)

    @app.post("/v1/embeddings", response_model=EmbeddingResponse, tags=["v1"])
    async def embeddings(req: EmbeddingRequest, request: Request) -> EmbeddingResponse:
        vectors = await request.app.state.embedder.embed(req.input)
        return EmbeddingResponse(
            model=request.app.state.settings.embedding_model
            if not req.model
            else req.model,
            dim=request.app.state.settings.embedding_dim,
            data=vectors,
        )

    # -----------------------------------------------------------------------
    # TASK-002 — collections / ingest / query / citations
    # -----------------------------------------------------------------------

    @app.post(
        "/v1/collections",
        response_model=CollectionInfo,
        status_code=status.HTTP_201_CREATED,
        tags=["v1"],
    )
    async def create_collection(req: CollectionCreate, request: Request) -> CollectionInfo:
        if not request.app.state.db_ready:
            raise HTTPException(status_code=503, detail="db not ready")
        pool = await _pool(request)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO collections (workspace, name, description)
                VALUES ($1, $2, $3)
                ON CONFLICT (workspace, name) DO UPDATE
                  SET description = COALESCE(EXCLUDED.description, collections.description)
                RETURNING id, workspace, name, description
                """,
                req.workspace,
                req.name,
                req.description,
            )
        return CollectionInfo(
            id=row["id"],
            workspace=row["workspace"],
            name=row["name"],
            description=row["description"],
        )

    @app.get("/v1/collections", response_model=list[CollectionInfo], tags=["v1"])
    async def list_collections(
        request: Request,
        workspace: str = Query(default="default", min_length=1, max_length=64),
    ) -> list[CollectionInfo]:
        if not request.app.state.db_ready:
            raise HTTPException(status_code=503, detail="db not ready")
        pool = await _pool(request)
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT c.id, c.workspace, c.name, c.description,
                       COUNT(DISTINCT d.id) AS document_count,
                       COUNT(ch.id)         AS chunk_count
                FROM collections c
                LEFT JOIN documents d ON d.workspace = c.workspace
                                     AND d.id IN (SELECT DISTINCT document_id FROM chunks WHERE collection_id = c.id)
                LEFT JOIN chunks ch ON ch.collection_id = c.id
                WHERE c.workspace = $1
                GROUP BY c.id
                ORDER BY c.id
                """,
                workspace,
            )
        return [
            CollectionInfo(
                id=r["id"],
                workspace=r["workspace"],
                name=r["name"],
                description=r["description"],
                document_count=r["document_count"],
                chunk_count=r["chunk_count"],
            )
            for r in rows
        ]

    @app.get(
        "/v1/collections/{col_id}",
        response_model=CollectionInfo,
        tags=["v1"],
    )
    async def get_collection(col_id: int, request: Request) -> CollectionInfo:
        if not request.app.state.db_ready:
            raise HTTPException(status_code=503, detail="db not ready")
        pool = await _pool(request)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT c.id, c.workspace, c.name, c.description,
                       COUNT(DISTINCT d.id) AS document_count,
                       COUNT(ch.id)         AS chunk_count
                FROM collections c
                LEFT JOIN documents d ON d.workspace = c.workspace
                                     AND d.id IN (SELECT DISTINCT document_id FROM chunks WHERE collection_id = c.id)
                LEFT JOIN chunks ch ON ch.collection_id = c.id
                WHERE c.id = $1
                GROUP BY c.id
                """,
                col_id,
            )
        if not row:
            raise HTTPException(status_code=404, detail="collection not found")
        return CollectionInfo(
            id=row["id"],
            workspace=row["workspace"],
            name=row["name"],
            description=row["description"],
            document_count=row["document_count"],
            chunk_count=row["chunk_count"],
        )

    @app.post("/v1/ingest", response_model=IngestResponse, tags=["v1"])
    async def ingest(
        request: Request,
        text: str | None = Form(default=None),
        file_name: str | None = Form(default=None),
        workspace: str = Form(default="default"),
        collection: str = Form(default="default"),
        upload: UploadFile | None = File(default=None),
    ) -> IngestResponse:
        if not request.app.state.db_ready:
            raise HTTPException(status_code=503, detail="db not ready")
        pool = await _pool(request)
        embedder = request.app.state.embedder
        try:
            if upload is not None:
                data = await upload.read()
                # Trust the upload filename; fall back to a sanitised
                # default if the client did not supply one.
                fname = upload.filename or file_name or "upload.md"
                result = await ingest_bytes(
                    pool=pool,
                    embedder=embedder,
                    data=data,
                    file_name=fname,
                    workspace=workspace,
                    collection_name=collection,
                    max_bytes=request.app.state.settings.ingest_max_bytes,
                    chunk_size=request.app.state.settings.chunk_size_chars,
                    chunk_overlap=request.app.state.settings.chunk_overlap_chars,
                )
            elif text is not None and file_name is not None:
                # Force the .md extension on the synthetic file name so the
                # format detector resolves it to markdown.
                fname = file_name if file_name.endswith(".md") else file_name + ".md"
                result = await ingest_text(
                    pool=pool,
                    embedder=embedder,
                    text=text,
                    workspace=workspace,
                    collection_name=collection,
                    source_label=fname,
                    max_bytes=request.app.state.settings.ingest_max_bytes,
                    chunk_size=request.app.state.settings.chunk_size_chars,
                    chunk_overlap=request.app.state.settings.chunk_overlap_chars,
                )
            else:
                raise IngestError(
                    "must supply either `upload` (file) or `text` + `file_name`"
                )
        except IngestError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return IngestResponse(
            document_id=result.document_id,
            collection_id=result.collection_id,
            chunks_created=result.chunks_created,
            content_sha=result.content_sha,
            chunk_hashes=result.chunk_hashes,
        )

    @app.post("/v1/query", response_model=QueryResponse, tags=["v1"])
    async def post_query(req: QueryRequest, request: Request) -> QueryResponse:
        if not request.app.state.db_ready:
            raise HTTPException(status_code=503, detail="db not ready")
        pool = await _pool(request)
        embedder = request.app.state.embedder
        settings: Settings = request.app.state.settings

        top_k = req.top_k or settings.retrieval_top_k
        result = await retrieve_query(
            pool=pool,
            embedder=embedder,
            question=req.question,
            collection_id=req.collection_id,
            workspace=req.workspace,
            top_k=top_k,
            threshold=settings.retrieval_min_score,
        )

        if not result.chunks or result.best_score < settings.retrieval_min_score:
            # REQ-004: explicit refusal. HTTP 200 (refusal is a normal
            # response) — a 4xx would imply the request is malformed.
            return QueryResponse(
                status="refused",
                question=req.question,
                reason=REFUSAL_REASON,
                citations=[],
                best_score=round(result.best_score, 4),
                threshold=settings.retrieval_min_score,
            )

        grounded = format_answer(result)
        return QueryResponse(
            status="answered",
            question=req.question,
            answer=grounded.answer,
            citations=grounded.citations,
            best_score=round(result.best_score, 4),
            threshold=settings.retrieval_min_score,
        )

    @app.get(
        "/v1/citations/{chunk_id}",
        response_model=ChunkDetail,
        tags=["v1"],
    )
    async def get_citation(chunk_id: int, request: Request) -> ChunkDetail:
        if not request.app.state.db_ready:
            raise HTTPException(status_code=503, detail="db not ready")
        pool = await _pool(request)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT c.id, c.document_id, c.content, c.content_sha,
                       c.workspace, c.collection_id, c.page, c.section,
                       d.source, d.file_name
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.id = $1
                """,
                chunk_id,
            )
        if not row:
            raise HTTPException(status_code=404, detail="chunk not found")
        return ChunkDetail(
            chunk_id=row["id"],
            document_id=row["document_id"],
            source_id=row["source"],
            file_name=row["file_name"],
            page=row["page"],
            section=row["section"],
            content=row["content"],
            content_sha=row["content_sha"],
            workspace=row["workspace"],
            collection_id=row["collection_id"],
        )

    return app


# Module-level for `uvicorn app.main:app`.
app = _build_app()


__all__ = ["app", "_build_app"]
