#!/usr/bin/env python3
"""Capture review-ready gallery screenshots for the publication kit.

This script runs INSIDE the test container, where Playwright + Chromium
are pre-installed and the API/UI services are reachable at the docker
service hostnames. It ingests the synthetic corpus into a fresh
workspace, then drives the static UI through four observable states:

  01-idle.png       — UI loaded, brand surface visible, no question yet
  02-answered.png   — on-topic question, citations rendered
  03-refused.png    — off-topic question, insufficient_evidence banner
  04-auth-error.png — UI surfaces the auth-error banner after a 401

The 401 is simulated via Playwright's `page.route()` so the demo does
not need to restart the API with AUTH_ENABLED=true. The genuine auth
contract is verified separately by `tests/e2e/test_ui_auth_gate.py`
and by the API-level smoke in `scripts/_demo_verify.py`.

The screenshots are written to the directory passed as $1 (a writable
directory the host script can extract with `docker cp`).
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright


API_URL = os.environ.get("API_URL", "http://api:8000")
UI_URL = os.environ.get("UI_URL", "http://ui:80")
CORPUS_DIR = Path(os.environ.get("CORPUS_DIR", "/srv/data/corpus"))


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


def _ingest_corpus(workspace: str) -> dict:
    """Ingest every supported file in the corpus into `workspace`."""
    files = sorted(
        p for p in CORPUS_DIR.iterdir()
        if p.suffix.lower() in {".md", ".markdown", ".txt", ".pdf"}
    )
    if not files:
        raise RuntimeError(f"corpus dir empty: {CORPUS_DIR}")

    collection = "gallery-corpus"
    collection_id = None
    ingested = 0
    with httpx.Client(base_url=API_URL, timeout=60.0) as client:
        # Idempotent collection creation.
        resp = client.post(
            "/v1/collections",
            json={"workspace": workspace, "name": collection, "description": "gallery demo"},
        )
        resp.raise_for_status()
        collection_id = resp.json()["id"]

        for path in files:
            mime = {
                ".md": "text/markdown",
                ".markdown": "text/markdown",
                ".txt": "text/plain",
                ".pdf": "application/pdf",
            }[path.suffix.lower()]
            with path.open("rb") as fh:
                r = client.post(
                    "/v1/ingest",
                    data={"workspace": workspace, "collection": collection},
                    files={"upload": (path.name, fh, mime)},
                )
            r.raise_for_status()
            ingested += 1

    return {
        "workspace": workspace,
        "collection": collection,
        "collection_id": collection_id,
        "files_ingested": ingested,
    }


def _shoot(page, out_path: Path) -> dict:
    """Save a full-viewport PNG and return its dimensions."""
    page.wait_for_load_state("networkidle", timeout=10_000)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_path), full_page=True)
    size = out_path.stat().st_size

    # Read PNG dimensions from the file header (no Pillow dependency).
    with out_path.open("rb") as fh:
        head = fh.read(24)
    # PNG signature (8) + IHDR length (4) + 'IHDR' (4) + width (4) + height (4)
    width = int.from_bytes(head[16:20], "big")
    height = int.from_bytes(head[20:24], "big")
    return {"path": str(out_path), "bytes": size, "width": width, "height": height}


def _wait_for_state(page, state: str, timeout_ms: int = 15_000) -> None:
    """Wait until #answer-state[data-state] equals `state`."""
    page.wait_for_function(
        "(s) => document.querySelector('#answer-state')?.getAttribute('data-state') === s",
        arg=state,
        timeout=timeout_ms,
    )


def main(out_dir: str) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    _wait_for_api()

    workspace = "gallery-" + uuid.uuid4().hex[:8]
    seed = _ingest_corpus(workspace)
    print(f"[demo] seeded workspace={workspace} files={seed['files_ingested']}", flush=True)

    ui_url = f"{UI_URL}?workspace={workspace}"

    results: dict[str, dict] = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()

        # --- 01-idle --------------------------------------------------
        page.goto(ui_url, wait_until="networkidle")
        page.wait_for_function(
            "document.querySelector('#answer-state')?.getAttribute('data-state') === 'idle'",
            timeout=10_000,
        )
        page.wait_for_function(
            "document.querySelector('html')?.getAttribute('data-identity') === 'ready'",
            timeout=10_000,
        )
        # Select the collection.
        page.wait_for_function(
            "document.querySelectorAll('#collection-select option').length >= 1",
            timeout=10_000,
        )
        values = page.evaluate(
            "Array.from(document.querySelectorAll('#collection-select option'))"
            ".map(o => o.value).filter(v => v)"
        )
        if values:
            page.locator("#collection-select").select_option(values[0])
        # Let the UI settle.
        page.wait_for_timeout(500)
        results["01-idle"] = _shoot(page, out / "01-idle.png")

        # --- 02-answered ----------------------------------------------
        page.locator("#question").fill(
            "What core vaccinations does a newly adopted dog need?"
        )
        page.locator("#ask").click()
        _wait_for_state(page, "answered")
        page.wait_for_timeout(300)
        results["02-answered"] = _shoot(page, out / "02-answered.png")

        # --- 03-refused -----------------------------------------------
        page.locator("#clear").click()
        page.locator("#question").fill(
            "What is the speed of light in a vacuum in metres per second?"
        )
        page.locator("#ask").click()
        _wait_for_state(page, "refused")
        page.wait_for_timeout(300)
        results["03-refused"] = _shoot(page, out / "03-refused.png")

        # --- 04-auth-error --------------------------------------------
        # Clear the form, install a route that returns 401 on /api/*, then
        # submit. The UI's #answer-state flips to 'error' and renders the
        # red banner with the bearer-token hint.
        page.locator("#clear").click()

        def _intercept_401(route):
            route.fulfill(
                status=401,
                headers={"content-type": "application/json"},
                body='{"detail":"missing or invalid bearer token"}',
            )

        page.route("**/api/v1/query*", _intercept_401)
        # Also intercept /api/v1/identity to keep the brand surface.
        page.route("**/api/v1/identity", lambda r: r.continue_())
        page.locator("#question").fill("Will this UI surface a 401?")
        page.locator("#ask").click()
        _wait_for_state(page, "error")
        page.wait_for_timeout(300)
        results["04-auth-error"] = _shoot(page, out / "04-auth-error.png")

        browser.close()

    return {
        "workspace": workspace,
        "seed": seed,
        "screenshots": results,
    }


if __name__ == "__main__":
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/gallery"
    info = main(out_dir)
    # Print a single JSON line so the host script can parse it.
    import json

    print("DEMO_JSON_BEGIN")
    print(json.dumps(info, indent=2, default=str))
    print("DEMO_JSON_END")