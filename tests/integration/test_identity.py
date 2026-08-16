"""Integration — REQ-006 identity surface.

`GET /v1/identity` is the public brand surface consumed by the UI at
load time. It must:
  - Be reachable without a Bearer token even when AUTH_ENABLED=true
    (the UI needs its brand BEFORE the user authenticates).
  - Reflect every operator-configurable value: brand_name, tagline,
    accent_color, logo_url, footer_note, auth_enabled, version.
  - Never expose a value that is not in the allow-list (CSS color guard
    on accent_color; logo_url is a plain string the operator chose).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import _build_app
from app.settings import Settings


def test_identity_endpoint_is_public_even_with_auth_enabled() -> None:
    """When AUTH_ENABLED=true, /v1/identity must NOT require a token."""
    settings = Settings(env_file=None)  # type: ignore[arg-type]
    settings.auth_enabled = True
    settings.auth_token = "real-token-xyz"
    app = _build_app(settings)
    with TestClient(app) as client:
        resp = client.get("/v1/identity")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["auth_enabled"] is True
        # The auth gate never ran on this path.
        assert "error" not in body


def test_identity_reflects_brand_name_override() -> None:
    settings = Settings(env_file=None)  # type: ignore[arg-type]
    settings.app_brand_name = "Custom KB"
    settings.app_tagline = "Inline test tagline"
    settings.app_footer_note = "Inline footer"
    settings.app_logo_url = ""
    app = _build_app(settings)
    with TestClient(app) as client:
        resp = client.get("/v1/identity")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["brand_name"] == "Custom KB"
        assert body["tagline"] == "Inline test tagline"
        assert body["footer_note"] == "Inline footer"


def test_identity_rejects_malformed_accent_color() -> None:
    """Bad accent_color is replaced by the safe default — never echoed back."""
    settings = Settings(env_file=None)  # type: ignore[arg-type]
    settings.app_accent_color = "javascript:alert(1)"  # CSS injection attempt
    app = _build_app(settings)
    with TestClient(app) as client:
        body = client.get("/v1/identity").json()
        assert body["accent_color"] == "#0284c7"


def test_identity_accepts_valid_accent_color_variants() -> None:
    settings = Settings(env_file=None)  # type: ignore[arg-type]
    for accent in ("#abc", "#aabbcc", "#aabbccdd", "rgb(1,2,3)", "rgba(1,2,3,0.5)"):
        settings.app_accent_color = accent
        app = _build_app(settings)
        with TestClient(app) as client:
            body = client.get("/v1/identity").json()
            assert body["accent_color"] == accent, accent


def test_identity_includes_version() -> None:
    app = _build_app()
    with TestClient(app) as client:
        body = client.get("/v1/identity").json()
        assert "version" in body
        assert isinstance(body["version"], str)
        assert body["version"]


def test_identity_route_does_not_emit_secret_like_payload() -> None:
    """Identity must never echo tokens, env, or upstream secrets."""
    app = _build_app()
    with TestClient(app) as client:
        body = client.get("/v1/identity").json()
    forbidden_keys = {
        "auth_token", "database_url", "embedding_api_key", "password",
    }
    for k in forbidden_keys:
        assert k not in body, body
        assert k not in {key.lower() for key in body.keys()}, body