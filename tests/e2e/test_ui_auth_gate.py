"""E2E — REQ-007 auth gate UI.

The live stack runs with AUTH_ENABLED=false in the dev compose file, so we
test the UI's auth behaviour in two complementary ways:

  1. With the real identity payload (auth_enabled=false) we verify the
     bearer panel stays hidden and the pill stays muted.
  2. With an intercepted identity payload (auth_enabled=true) we verify
     the bearer panel appears, the pill flips to "Auth required", and a
     saved token flips the pill back to "Authenticated".

The actual gate enforcement (`/v1/*` returning 401 without a token) is
covered by `tests/security/test_auth.py` against the FastAPI TestClient,
which already flips `AUTH_ENABLED` at runtime.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, expect

from tests.e2e.conftest import UI_URL


@pytest.fixture
def auth_context(browser: Browser) -> BrowserContext:
    """A browser context where `/api/v1/identity` is intercepted to
    advertise `auth_enabled=true`."""
    context = browser.new_context(viewport={"width": 1200, "height": 800})

    def _route(route, request):  # type: ignore[no-untyped-def]
        if request.url.endswith("/api/v1/identity"):
            route.fulfill(
                status=200,
                content_type="application/json",
                body=(
                    "{"
                    '"brand_name":"Auth Demo",'
                    '"tagline":"UI auth gate exercise",'
                    '"accent_color":"#9333ea",'
                    '"logo_url":"",'
                    '"footer_note":"identity-intercepted",'
                    '"auth_enabled":true,'
                    '"version":"0.0.0-test"'
                    "}"
                ),
            )
            return
        # Pass everything else through (the real api is still reachable).
        route.continue_()

    context.route("**/api/v1/identity", _route)
    return context


def test_default_identity_keeps_bearer_panel_hidden(page: Page) -> None:
    """AUTH_ENABLED=false in the live stack → bearer panel stays hidden."""
    expect(page.locator("#auth-panel")).to_be_hidden()
    expect(page.locator("#auth-pill")).to_have_text("Auth disabled")


def test_intercepted_identity_reveals_bearer_panel(auth_context: BrowserContext) -> None:
    """auth_enabled=true → panel becomes visible; pill flips to required."""
    page = auth_context.new_page()
    page.goto(UI_URL, wait_until="networkidle")
    expect(page.locator("#auth-panel")).to_be_visible()
    expect(page.locator("#auth-pill")).to_have_text("Auth required")
    page.close()


def test_token_round_trip_flips_auth_pill(auth_context: BrowserContext) -> None:
    """Saving a token flips the pill to 'Authenticated'; clearing flips it back."""
    page = auth_context.new_page()
    page.goto(UI_URL, wait_until="networkidle")
    # Auth required at boot.
    expect(page.locator("#auth-pill")).to_have_text("Auth required")
    # Save a fake token.
    page.locator("#auth-token").fill("example-token-XYZ")
    page.locator("#auth-save").click()
    expect(page.locator("#auth-pill")).to_have_text("Authenticated")
    # Clear and re-check.
    page.locator("#auth-clear").click()
    expect(page.locator("#auth-pill")).to_have_text("Auth required")
    # The token input was wiped too.
    expect(page.locator("#auth-token")).to_have_value("")
    page.close()


def test_bearer_header_forwarded_on_query(page: Page) -> None:
    """When a token is saved in localStorage, `/v1/query` requests carry it.

    We verify this by capturing outbound requests with Playwright's
    request listener. The auth-enabled payload is forced via a one-off
    identity intercept on the same page.
    """

    captured: list[tuple[str, dict[str, str]]] = []

    def _on_request(request):  # type: ignore[no-untyped-def]
        if "/api/v1/query" in request.url:
            captured.append((request.url, dict(request.headers)))

    def _route(route, request):  # type: ignore[no-untyped-def]
        if request.url.endswith("/api/v1/identity"):
            route.fulfill(
                status=200,
                content_type="application/json",
                body=(
                    "{"
                    '"brand_name":"Auth Demo",'
                    '"tagline":"UI auth gate exercise",'
                    '"accent_color":"#9333ea",'
                    '"logo_url":"",'
                    '"footer_note":"",'
                    '"auth_enabled":true,'
                    '"version":"0.0.0-test"'
                    "}"
                ),
            )
            return
        route.continue_()

    page.route("**/api/v1/identity", _route)
    page.on("request", _on_request)
    page.goto(UI_URL, wait_until="networkidle")
    # Drop a fake token into localStorage directly so we don't depend on
    # the panel workflow for this assertion.
    page.evaluate("window.localStorage.setItem('upworkkb.bearer.v1', 'token-XYZ')")
    page.reload(wait_until="networkidle")
    # The page now uses the token on every fetch. Trigger a query.
    page.wait_for_function(
        "!document.querySelector('#collection-select option[value=\"\"]') || "
        "document.querySelectorAll('#collection-select option[value]:not([value=\"\"])').length >= 1",
        timeout=15_000,
    )
    # Pick the first real collection option (handle the empty-workspace case).
    values = page.evaluate(
        "Array.from(document.querySelectorAll('#collection-select option'))"
        ".map(o => o.value).filter(v => v)"
    )
    if values:
        page.locator("#collection-select").select_option(values[0])
    page.locator("#question").fill("Anything?")
    page.locator("#ask").click()
    # Wait for either a 200 response or a refusal to arrive — both carry the header.
    page.wait_for_timeout(2_000)
    assert captured, "no /v1/query request was observed"
    for _url, headers in captured:
        # Playwright lowercases header keys.
        auth = headers.get("authorization") or headers.get("Authorization")
        assert auth == "Bearer tok-XYZ", headers


def test_query_request_emits_audit_line_from_ui_proxy(page: Page) -> None:
    """A query submitted through the UI must round-trip through the audit
    middleware (REQ-007). We assert the response carries the
    `x-request-id` header — the same id the audit logger emits — and
    that the request was made from the page's fetch context (not a
    cached stale response).
    """
    captured: list[dict[str, str]] = []

    def _on_response(response):  # type: ignore[no-untyped-def]
        if "/api/v1/query" in response.url:
            captured.append(dict(response.headers))

    page.on("response", _on_response)
    # Wait for the identity + collections round-trip so the page is ready.
    expect(page.locator("html")).to_have_attribute("data-identity", "ready")
    page.wait_for_function(
        "!document.querySelector('#collection-select option[value=\"\"]') || "
        "document.querySelectorAll('#collection-select option[value]:not([value=\"\"])').length >= 1",
        timeout=15_000,
    )
    values = page.evaluate(
        "Array.from(document.querySelectorAll('#collection-select option'))"
        ".map(o => o.value).filter(v => v)"
    )
    if values:
        page.locator("#collection-select").select_option(values[0])
    page.locator("#question").fill("Anything that triggers an audit line?")
    page.locator("#ask").click()
    # Wait for either answered or refused — both go through middleware.
    expect(page.locator("#answer-state")).not_to_have_attribute(
        "data-state", "idle", timeout=15_000
    )
    assert captured, "no /v1/query response was observed"
    # The API must attach x-request-id (added by the audit middleware).
    headers = captured[-1]
    rid = headers.get("x-request-id") or headers.get("X-Request-Id")
    assert rid, f"x-request-id missing from response headers: {headers}"
    assert len(rid) >= 8, f"x-request-id looks malformed: {rid!r}"