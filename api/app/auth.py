"""Minimal Bearer-token gate (REQ-007 foundation).

`AUTH_ENABLED=false` keeps dev open. When enabled, every `/v1/*` call must
carry an `Authorization: Bearer <token>` header matching `AUTH_TOKEN`.
Comparison uses `secrets.compare_digest` to avoid timing leaks.

This is intentionally minimal. Production should wire in a real IdP — that is
out of TASK-001 scope.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass


@dataclass(frozen=True)
class AuthResult:
    allowed: bool
    principal: str | None
    reason: str | None = None


def check_bearer(
    *,
    enabled: bool,
    expected_token: str,
    presented_header: str | None,
    request_path: str = "",
) -> AuthResult:
    """Validate a Bearer token. Pure function — easy to unit-test."""

    # Public health + brand endpoints are always reachable regardless of
    # auth. The UI must be able to render its own brand BEFORE the user
    # supplies a token — `/v1/identity` is therefore a public surface
    # even when AUTH_ENABLED=true.
    if request_path in {"/healthz", "/readyz", "/v1/identity"}:
        return AuthResult(allowed=True, principal="anonymous-public", reason="public-endpoint")

    if not enabled:
        return AuthResult(allowed=True, principal="anonymous-dev", reason="auth-disabled")

    if not presented_header:
        return AuthResult(allowed=False, principal=None, reason="missing-authorization-header")

    parts = presented_header.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return AuthResult(allowed=False, principal=None, reason="malformed-authorization-header")

    token = parts[1].strip()
    if not token:
        return AuthResult(allowed=False, principal=None, reason="empty-token")

    if not expected_token or expected_token.startswith("replace-with"):
        return AuthResult(
            allowed=False,
            principal=None,
            reason="server-auth-token-not-configured",
        )

    if not secrets.compare_digest(token, expected_token):
        return AuthResult(allowed=False, principal=None, reason="token-mismatch")

    return AuthResult(allowed=True, principal="bearer-token-holder", reason="token-ok")


__all__ = ["AuthResult", "check_bearer"]
