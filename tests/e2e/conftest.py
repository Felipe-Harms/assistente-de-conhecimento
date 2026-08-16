"""E2E fixtures for the Playwright-driven UI tests (REQ-006 / REQ-007).

These tests run INSIDE the test container, which sits on the same
docker `backend` network as the `api`, `ui` and `db` services. We hit the
static UI through `http://ui:80` and the API through `http://api:8000`
directly when we need to seed the corpus.

`ingested_corpus` ingests the synthetic corpus into a fresh workspace so
each test gets a clean answerable question plus a clearly out-of-domain
refusal question.

We deliberately do NOT pin Playwright fixtures at session scope — each
test gets a fresh browser context so localStorage / cookies do not leak
between tests, especially the auth-token one.
"""

from __future__ import annotations

import hashlib
import os
import time
import uuid
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

# Inside the test container the test directory lives at /srv/tests; the
# corpus is mirrored at /srv/data/corpus (the api image also reads it).
CORPUS_DIR = Path(os.environ.get("CORPUS_DIR", "/srv/data/corpus"))

UI_URL = os.environ.get("UI_URL", "http://ui:80")
API_URL = os.environ.get("API_URL", "http://api:8000")

# A unique workspace per test so concurrent E2E runs do not collide on
# data — E2E tests run slower than the unit suite and benefit from the
# same isolation discipline.
WORKSPACE_PREFIX = "e2e-"


def _wait_for_api(timeout_s: float = 60.0) -> None:
    deadline = time.time() + timeout_s
    last: Exception | None = None
    while time.time() < deadline:
        try:
            r = httpx.get(f"{API_URL}/healthz", timeout=2.0)
            if r.status_code == 200:
                return
        except Exception as exc:
            last = exc
        time.sleep(0.5)
    raise RuntimeError(f"API not reachable at {API_URL}: {last}")


@pytest.fixture(scope="session", autouse=True)
def _e2e_preflight() -> None:
    _wait_for_api()


@pytest.fixture
def workspace_id() -> str:
    return WORKSPACE_PREFIX + uuid.uuid4().hex[:8]


@pytest.fixture
def ingested_corpus(workspace_id: str):
    """Ingest the synthetic corpus into a fresh workspace.

    Returns a dict with: workspace_id, collection_id, file_count,
    chunk_count. The fixture cleans up after the test only by relying on
    workspace isolation; nothing mutates the schema.
    """
    ingest_url = f"{API_URL}/v1/ingest"
    collection = "e2e-corpus"
    files = sorted(
        p for p in CORPUS_DIR.iterdir() if p.suffix.lower() in {".md", ".markdown", ".txt", ".pdf"}
    )
    if not files:
        pytest.skip(f"corpus dir empty: {CORPUS_DIR}")

    ingested = 0
    collection_id = None
    with httpx.Client(base_url=API_URL, timeout=60.0) as client:
        for path in files:
            mime = {
                ".md": "text/markdown",
                ".markdown": "text/markdown",
                ".txt": "text/plain",
                ".pdf": "application/pdf",
            }[path.suffix.lower()]
            with path.open("rb") as fh:
                resp = client.post(
                    ingest_url,
                    data={"workspace": workspace_id, "collection": collection},
                    files={"upload": (path.name, fh, mime)},
                )
            assert resp.status_code == 200, (
                f"ingest {path.name} failed: {resp.status_code} {resp.text}"
            )
            body = resp.json()
            ingested += 1
            collection_id = body["collection_id"]
        # Also fetch /v1/collections so the E2E test can use it directly.
        listed = client.get(
            f"{API_URL}/v1/collections", params={"workspace": workspace_id}
        )
        assert listed.status_code == 200, listed.text
        cols = listed.json()
    return {
        "workspace_id": workspace_id,
        "collection_id": collection_id,
        "collection_name": collection,
        "file_count": ingested,
        "chunk_count": sum(c.get("chunk_count", 0) for c in cols),
        "collections": cols,
    }


@pytest.fixture(scope="session")
def _playwright() -> "object":
    """Session-scoped Playwright handle; yields a manager-like object."""
    pw = sync_playwright().start()
    try:
        yield pw
    finally:
        pw.stop()


@pytest.fixture
def browser(_playwright) -> Browser:
    """Function-scoped chromium — fresh process per test.

    The browsers share the chromium binary but each test gets a clean
    context with no shared localStorage. This matters because the auth
    test relies on localStorage being empty at boot.
    """
    return _playwright.chromium.launch(headless=True)


@pytest.fixture
def context(browser: Browser) -> BrowserContext:
    """Function-scoped browser context with no traces / no storage leaks."""
    return browser.new_context(viewport={"width": 1200, "height": 800})


@pytest.fixture
def page(context: BrowserContext, ui_url: "str") -> Page:
    """Navigate to the UI before the test runs so `page` is already at /."""
    p = context.new_page()
    p.goto(ui_url, wait_until="networkidle")
    yield p
    p.close()


@pytest.fixture
def page_in_workspace(context: BrowserContext, ui_url: "str"):
    """Page factory that loads the UI pinned to a specific workspace via
    `?workspace=…`. Tests pass the fixture's workspace id and receive a
    Page already pointed at the right workspace."""
    def _make(workspace: str) -> Page:
        sep = "&" if "?" in ui_url else "?"
        p = context.new_page()
        p.goto(f"{ui_url}{sep}workspace={workspace}", wait_until="networkidle")
        return p
    return _make


@pytest.fixture(scope="session")
def ui_url() -> str:
    return UI_URL


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()