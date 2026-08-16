"""Shared pytest fixtures.

Security tests use `api_client` (in-process, per-function). Integration
and acceptance tests use `app_client` (function-scoped, with a fresh DB
pool per test). The pool is created in the TestClient's event loop and
torn down in the same loop after the test — this avoids the cross-loop
asynpg error that a session-scoped pool would hit when the TestClient
moves between event loops.

`fresh_workspace` is a per-test workspace id so concurrent test runs
don't collide on the same data.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

# Force `.env` to be ignored even if a developer has one locally.
os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("EMBEDDING_STUB", "true")

import pytest
from fastapi.testclient import TestClient

from app.main import _build_app  # noqa: E402  (after env setup)

# Repo root — used to locate the synthetic corpus. The test container
# mirrors /srv/{api,tests,data,proof,repo,...} — the test file lives at
# /srv/tests/integration/test_*.py, so parents[1] = /srv.
REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = REPO_ROOT / "data" / "corpus"


@pytest.fixture
def fresh_workspace() -> str:
    """Unique workspace per test — guarantees isolation even when the suite
    runs in parallel."""
    return f"test-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def app_client():
    """Per-test FastAPI TestClient with a fresh DB pool.

    The asyncpg pool is bound to the event loop that created it. A
    session-scoped pool would re-enter the pool from a different loop on
    subsequent tests (because Starlette's TestClient creates a new
    portal/loop per `with` block), hitting `cannot perform operation:
    another operation is in progress`. Per-test pool reset guarantees
    the pool's loop and the test's request loop are identical.

    The integration + acceptance suites are small (< 20 tests); the
    per-test pool reset cost is negligible.
    """
    from app import db as db_module
    from app.settings import Settings

    async def _reset() -> None:
        if db_module._pool is not None:
            await db_module._pool.close()
            db_module._pool = None
            db_module._registered_dim = None

    app = _build_app(Settings(env_file=None))  # type: ignore[arg-type]
    with TestClient(app) as client:
        # Reset any leftover pool from a previous test in the SAME loop
        # as the TestClient's portal. Using the portal's `.call` ensures
        # `await pool.close()` runs in the loop that owns the pool.
        client.portal.call(_reset)
        # Warm up the pool in the TestClient's loop.
        resp = client.get("/readyz")
        assert resp.status_code == 200, resp.text
        assert resp.json()["components"]["db"] == "ok", resp.text
        yield client
        # Tear down the pool so the next test gets a fresh one bound to
        # the new TestClient's loop.
        client.portal.call(_reset)


@pytest.fixture
def api_client():
    """Per-test FastAPI client with lifespan triggered.

    Used by the security suite. Boots a fresh app per test so the tests
    can inspect env overrides without polluting the session-scoped
    `app_client`.
    """
    app = _build_app()
    with TestClient(app) as client:
        yield client
