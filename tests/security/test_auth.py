"""Security smoke tests — REQ-007: minimal auth gate behaviour."""

from __future__ import annotations

import pytest

from app.auth import AuthResult, check_bearer


def test_auth_disabled_allows_anonymous() -> None:
    out = check_bearer(
        enabled=False,
        expected_token="unused",
        presented_header=None,
        request_path="/v1/embeddings",
    )
    assert out.allowed is True
    assert out.principal == "anonymous-dev"


def test_auth_enabled_requires_bearer() -> None:
    out = check_bearer(
        enabled=True,
        expected_token="real-token",
        presented_header=None,
        request_path="/v1/embeddings",
    )
    assert out.allowed is False
    assert out.reason == "missing-authorization-header"


def test_auth_enabled_with_wrong_token_denies() -> None:
    out = check_bearer(
        enabled=True,
        expected_token="real-token",
        presented_header="Bearer wrong",
        request_path="/v1/embeddings",
    )
    assert out.allowed is False
    assert out.reason == "token-mismatch"


def test_auth_enabled_with_correct_token_allows() -> None:
    out = check_bearer(
        enabled=True,
        expected_token="real-token",
        presented_header="Bearer real-token",
        request_path="/v1/embeddings",
    )
    assert out.allowed is True
    assert out.principal == "bearer-token-holder"


def test_health_routes_bypass_auth_gate() -> None:
    """Even when AUTH_ENABLED, /healthz and /readyz are public."""
    out = check_bearer(
        enabled=True,
        expected_token="real-token",
        presented_header=None,
        request_path="/healthz",
    )
    assert out.allowed is True
    # All public surfaces share the same principal label so the audit
    # log can group them. The exact string is an implementation detail
    # but must be one of the documented public principals.
    assert out.principal in {"anonymous-health", "anonymous-public"}


def test_identity_route_bypasses_auth_gate() -> None:
    """The UI must be able to fetch its own brand BEFORE authentication."""
    out = check_bearer(
        enabled=True,
        expected_token="real-token",
        presented_header=None,
        request_path="/v1/identity",
    )
    assert out.allowed is True
    assert out.principal == "anonymous-public"


def test_malformed_authorization_header_rejected() -> None:
    out = check_bearer(
        enabled=True,
        expected_token="real-token",
        presented_header="Token foo",  # wrong scheme
        request_path="/v1/embeddings",
    )
    assert out.allowed is False
    assert out.reason == "malformed-authorization-header"


def test_auth_rejects_unconfigured_server_token() -> None:
    out = check_bearer(
        enabled=True,
        expected_token="replace-with-long-random-token",  # the .env default
        presented_header="Bearer replace",
        request_path="/v1/embeddings",
    )
    assert out.allowed is False
    assert out.reason == "server-auth-token-not-configured"


def test_api_protects_v1_with_auth(monkeypatch) -> None:
    """Smoke: when AUTH_ENABLED flips on at runtime, /v1/* is gated."""
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_TOKEN", "real-token-xyz")

    from app.settings import Settings
    from app.main import _build_app
    from fastapi.testclient import TestClient

    app = _build_app(Settings(env_file=None))  # type: ignore[arg-type]
    with TestClient(app) as client:
        # Without token: gated.
        r = client.post("/v1/embeddings", json={"input": ["hi"]})
        assert r.status_code == 401, r.text

        # With correct token: open.
        r = client.post(
            "/v1/embeddings",
            json={"input": ["hi"]},
            headers={"Authorization": "Bearer real-token-xyz"},
        )
        assert r.status_code == 200, r.text

        # Health stays public.
        r = client.get("/healthz")
        assert r.status_code == 200
