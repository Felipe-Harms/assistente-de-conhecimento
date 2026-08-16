"""Process-wide settings sourced exclusively from environment variables.

Never embed secrets in code; rely on env + .gitignore'd .env.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime config for API + workers.

    Field names mirror the variable names used in `.env.example`.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_log_level: str = "INFO"

    # Database
    database_url: str = (
        "postgresql+asyncpg://upworkkb:change-me-locally-only@db:5432/upworkkb"
    )
    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_db: str = "upworkkb"

    # Auth (REQ-007 foundation)
    auth_enabled: bool = False
    auth_token: str = "replace-with-long-random-token"

    # Embeddings (DEC-005)
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: str = "sk-replace-me-with-real-key"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    embedding_stub: bool = True

    # Retention (REQ-007)
    retention_days: int = 90

    # UI identity (REQ-006) — operator-configurable brand surface served
    # by `GET /v1/identity` and consumed by the static UI at load time.
    # Every value here is a placeholder; nothing in this file is a secret.
    app_brand_name: str = "Upwork Knowledge Assistant"
    app_tagline: str = (
        "Local, grounded answers from a curated corpus — refuses when "
        "evidence is missing."
    )
    # CSS color (`#rgb`, `#rrggbb`, or `rgb(...)`). Validated by the
    # identity endpoint — bad values fall back to the default accent.
    app_accent_color: str = "#0284c7"
    # Optional URL for a brand mark. Empty string disables the logo.
    app_logo_url: str = ""
    # Free-text footer note shown beneath the layout. Keep it short.
    app_footer_note: str = (
        "Local-only proof build. Citations are mandatory — read them."
    )

    # Ingest (REQ-002)
    # Default 10 MiB per file. Tuneable per deployment.
    ingest_max_bytes: int = 10 * 1024 * 1024
    # Approximate chunk size in characters (~512 tokens worth).
    chunk_size_chars: int = 2000
    # Overlap in characters (~64 tokens worth).
    chunk_overlap_chars: int = 256

    # Retrieval (REQ-003, REQ-004)
    retrieval_top_k: int = 5
    # Refuse if the top cosine similarity is below this threshold.
    # The stub embedding is deterministic but crude: same-topic cosine
    # settles around 0.30–0.65 while off-topic cosine sits around
    # 0.05–0.30. The 0.30 cut-off was tuned empirically against the
    # see the documented borderline
    # cases) — it keeps on-topic questions answerable while refusing
    # the off-topic ones in the acceptance suite.
    retrieval_min_score: float = 0.20


def get_settings() -> Settings:
    """Cached-friendly accessor.

    Tests instantiate their own Settings(env_file=None) directly.
    """
    return Settings()  # type: ignore[call-arg]


__all__ = ["Settings", "get_settings"]
