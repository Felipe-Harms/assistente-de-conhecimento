"""Pydantic input/output models (REQ-007: input validation baseline)."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_QUERY_CHARS = 4_000
MAX_PAYLOAD_BYTES = 64 * 1024  # 64 KiB hard cap per request
MAX_COLLECTION_NAME = 128
MAX_QUESTION_CHARS = 2_000


class HealthResponse(BaseModel):
    """Response shape for `/healthz`."""

    status: str = "ok"
    version: str
    auth_enabled: bool


class ReadyResponse(BaseModel):
    """Response shape for `/readyz`. Tells us deps (db) are reachable."""

    status: str
    components: dict[str, str] = Field(default_factory=dict)


class EmbeddingRequest(BaseModel):
    """Stub input used by `/v1/embeddings`."""

    model_config = ConfigDict(extra="forbid")

    input: list[str] = Field(min_length=1, max_length=64)
    model: str | None = None

    @field_validator("input")
    @classmethod
    def _validate_input(cls, value: list[str]) -> list[str]:
        for item in value:
            if not isinstance(item, str):
                raise ValueError("input must be list[str]")
            if len(item) == 0:
                raise ValueError("input entries must be non-empty")
            if len(item) > MAX_QUERY_CHARS:
                raise ValueError(
                    f"input entries must be <= {MAX_QUERY_CHARS} characters"
                )
            if "\x00" in item:
                raise ValueError("input entries must not contain NUL bytes")
        return value


class EmbeddingResponse(BaseModel):
    """Stub response used by `/v1/embeddings`. Real schema lands in TASK-002."""

    model: str
    dim: int
    data: list[list[float]]


class ErrorEnvelope(BaseModel):
    """Uniform error shape for 4xx/5xx responses."""

    error: dict[str, Any]


# ---------------------------------------------------------------------------
# TASK-002 — ingest / query / collections
# ---------------------------------------------------------------------------

class IngestRequest(BaseModel):
    """Inline-text ingest. Multipart uses the `IngestUploadResponse` directly."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=200_000)
    file_name: str = Field(min_length=1, max_length=256)
    workspace: str = Field(default="default", min_length=1, max_length=64)
    collection: str = Field(min_length=1, max_length=128)


class IngestResponse(BaseModel):
    document_id: int
    collection_id: int
    chunks_created: int
    content_sha: str
    chunk_hashes: list[str]


class CollectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_COLLECTION_NAME)
    workspace: str = Field(default="default", min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=512)


class CollectionInfo(BaseModel):
    id: int
    workspace: str
    name: str
    description: str | None = None
    document_count: int = 0
    chunk_count: int = 0


class IdentityResponse(BaseModel):
    """Public, non-sensitive identity surface (REQ-006).

    Served by `GET /v1/identity` so the static UI can render the brand
    without needing environment access at build time. Always public —
    the UI must be able to render its own brand before the user types
    a token.
    """

    brand_name: str
    tagline: str
    accent_color: str
    logo_url: str
    footer_note: str
    auth_enabled: bool
    version: str


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    collection_id: int = Field(gt=0)
    workspace: str = Field(default="default", min_length=1, max_length=64)
    top_k: int | None = Field(default=None, gt=0, le=32)


class QueryResponse(BaseModel):
    """The public refusal / answer envelope.

    - `status="answered"`   → `answer` and `citations` are populated.
    - `status="refused"`    → `reason="insufficient_evidence"`, `citations=[]`.
    """

    status: str
    question: str
    answer: str | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    reason: str | None = None
    best_score: float | None = None
    threshold: float | None = None


class ChunkDetail(BaseModel):
    chunk_id: int
    document_id: int
    source_id: str
    file_name: str
    page: int | None
    section: str | None
    content: str
    content_sha: str
    workspace: str
    collection_id: int | None
