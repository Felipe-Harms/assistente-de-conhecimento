"""E2E — UX improvements (M-1..M-5 + m-3).

Five improvements adopted from publication/UX-REVIEW.md:

- M-1: citation cards are clickable anchors; inline `[N]` markers in
  the answer body become anchor links pointing to the matching card.
- M-2: error banner has a friendly title + a primary action button
  ("Open token settings" for 401, "Retry" for 5xx / network); the raw
  message lives inside a collapsed <details>.
- M-3: empty-collection state is actionable, not a dead-end.
- M-4: long-answer citations collapse under <details>/<summary> when
  the answer carries more than `expandTop` citations (desktop = 3,
  mobile = 1).
- M-5: primary buttons and the collection selector have a hit area
  ≥ 44 px (Apple/Google HIG).
- m-3: buttons carry a styled :focus-visible outline that matches the
  input/textarea accent outline.

These tests run inside the test container alongside the existing
auth-gate / query-flow / smoke tests. We deliberately keep them
function-scoped so each test gets a fresh browser context — no
localStorage leakage between error-banner tests.
"""

from __future__ import annotations

import re
import uuid

import pytest
from playwright.sync_api import Page, BrowserContext, expect

from tests.e2e.conftest import UI_URL, ingested_corpus as _shared_ingested_corpus


# A local alias of the query-flow fixture so this test file stays
# self-contained (pytest fixtures do not cross test modules unless
# they live in conftest.py). The shape is identical.
@pytest.fixture
def populated_page(page_in_workspace, ingested_corpus, context) -> Page:
    """Boot the UI pinned to the test workspace; pre-select its collection."""
    page = page_in_workspace(ingested_corpus["workspace_id"])
    expect(page.locator("html")).to_have_attribute("data-identity", "ready")
    page.wait_for_function(
        "document.querySelectorAll('#collection-select option[value]:not([value=\"\"])').length >= 1",
        timeout=15_000,
    )
    value = page.evaluate(
        "Array.from(document.querySelectorAll('#collection-select option'))"
        ".map(o => o.value).filter(v => v)[0]"
    )
    if value:
        page.locator("#collection-select").select_option(value)
    yield page
    page.close()
    context.close()


def _pick_first_collection_value(page: Page) -> str:
    """Return the value of the first non-placeholder option in the
    collection selector. Tests pin the value (not the index) so the
    assertion is robust against placeholder/index rearrangements."""
    page.wait_for_function(
        "document.querySelectorAll('#collection-select option[value]:not([value=\"\"])').length >= 1",
        timeout=15_000,
    )
    return page.evaluate(
        "Array.from(document.querySelectorAll('#collection-select option'))"
        ".map(o => o.value).filter(v => v)[0]"
    )


# ----- M-1: citation cards are clickable anchors --------------------

def test_citation_cards_have_anchor_href(populated_page: Page) -> None:
    """M-1: every citation card is wrapped in <a class="citation-anchor">."""
    populated_page.locator("#question").fill(
        "What core vaccinations does a newly adopted dog need?"
    )
    populated_page.locator("#ask").click()
    expect(populated_page.locator("#answer-state")).to_have_attribute(
        "data-state", "answered", timeout=15_000
    )
    anchors = populated_page.locator("#citations a.citation-anchor")
    count = anchors.count()
    assert count >= 1, f"no .citation-anchor found (got {count})"
    # Each anchor must have a stable href pointing to its own id.
    for i in range(count):
        href = anchors.nth(i).get_attribute("href")
        assert href == f"#citation-{i + 1}", href
    # The matching <li> has the same id (so the anchor scrolls to it).
    li_ids = populated_page.locator("#citations li.citation").evaluate_all(
        "els => els.map(e => e.id)"
    )
    assert li_ids == [f"citation-{i + 1}" for i in range(count)], li_ids


def test_inline_citation_markers_become_anchor_links(
    populated_page: Page,
) -> None:
    """M-1: inline `[N]` markers in the answer become anchor links."""
    populated_page.locator("#question").fill(
        "What core vaccinations does a newly adopted dog need?"
    )
    populated_page.locator("#ask").click()
    expect(populated_page.locator("#answer-state")).to_have_attribute(
        "data-state", "answered", timeout=15_000
    )
    links = populated_page.locator("#answer a.citation-link")
    n = links.count()
    assert n >= 1, (
        "no inline .citation-link found — the inline `[N]` markers are "
        "still plain text"
    )
    # Each link's href must point to the matching citation card.
    for i in range(n):
        href = links.nth(i).get_attribute("href")
        assert href == f"#citation-{i + 1}", href


# ----- M-2: 401 / 5xx banners with action buttons -------------------

def _identity_with_auth_enabled() -> bytes:
    return (
        b"{"
        b'"brand_name":"Auth Demo",'
        b'"tagline":"",'
        b'"accent_color":"#0284c7",'
        b'"logo_url":"",'
        b'"footer_note":"",'
        b'"auth_enabled":true,'
        b'"version":"0.0.0-test"'
        b"}"
    )


def _identity_auth_disabled() -> bytes:
    return (
        b"{"
        b'"brand_name":"Retry Demo",'
        b'"tagline":"",'
        b'"accent_color":"#0284c7",'
        b'"logo_url":"",'
        b'"footer_note":"",'
        b'"auth_enabled":false,'
        b'"version":"0.0.0-test"'
        b"}"
    )


def test_401_error_banner_shows_open_token_settings_action(
    context: BrowserContext,
) -> None:
    """M-2: a simulated 401 surfaces the friendly banner + the
    'Open token settings' action button."""
    page = context.new_page()

    def _route(route, request):  # type: ignore[no-untyped-def]
        if request.url.endswith("/api/v1/identity"):
            route.fulfill(
                status=200,
                content_type="application/json",
                body=_identity_with_auth_enabled(),
            )
            return
        if "/api/v1/query" in request.url:
            route.fulfill(
                status=401,
                content_type="application/json",
                body=b'{"error":{"message":"HTTP 401"}}',
            )
            return
        route.continue_()

    page.route("**/api/v1/**", _route)
    page.goto(UI_URL, wait_until="networkidle")
    page.evaluate("window.localStorage.setItem('upworkkb.bearer.v1', 'stale-token')")
    page.reload(wait_until="networkidle")
    cid = _pick_first_collection_value(page)
    page.locator("#collection-select").select_option(cid)
    page.locator("#question").fill("Will this surface a 401?")
    page.locator("#ask").click()
    expect(page.locator("#answer-state")).to_have_attribute(
        "data-state", "error", timeout=15_000
    )
    banner = page.locator(".error-banner")
    expect(banner).to_be_visible()
    assert "Unauthorized" in banner.inner_text(), banner.inner_text()
    btn = page.locator('.error-banner button[data-action="open-token-settings"]')
    expect(btn).to_be_visible()
    expect(btn).to_have_text(re.compile(r"Open token settings"))
    # The raw technical details live inside a collapsed <details>.
    expect(page.locator(".error-banner details.error-banner-raw")).to_be_visible()
    page.close()


def test_5xx_error_banner_shows_retry_action(context: BrowserContext) -> None:
    """M-2: a simulated 5xx surfaces the friendly banner + the
    'Retry' action button."""
    page = context.new_page()

    def _route(route, request):  # type: ignore[no-untyped-def]
        if request.url.endswith("/api/v1/identity"):
            route.fulfill(
                status=200,
                content_type="application/json",
                body=_identity_auth_disabled(),
            )
            return
        if "/api/v1/query" in request.url:
            route.fulfill(
                status=503,
                content_type="application/json",
                body=b'{"error":{"message":"backend unavailable"}}',
            )
            return
        route.continue_()

    page.route("**/api/v1/**", _route)
    page.goto(UI_URL, wait_until="networkidle")
    cid = _pick_first_collection_value(page)
    page.locator("#collection-select").select_option(cid)
    page.locator("#question").fill("Will this surface a 503?")
    page.locator("#ask").click()
    expect(page.locator("#answer-state")).to_have_attribute(
        "data-state", "error", timeout=15_000
    )
    banner = page.locator(".error-banner")
    expect(banner).to_be_visible()
    btn = page.locator('.error-banner button[data-action="retry-query"]')
    expect(btn).to_be_visible()
    expect(btn).to_have_text(re.compile(r"Retry"))
    page.close()


# ----- M-3: empty-collection state is actionable --------------------

def test_empty_collection_state_surfaces_actionable_message(
    context: BrowserContext,
) -> None:
    """M-3: bootstrap a fresh workspace with no collections ingested →
    the answer card switches to an actionable empty-state placeholder."""
    # Build a workspace that has zero collections by using a brand-new
    # workspace id without ingesting anything.
    empty_ws = "e2e-empty-" + uuid.uuid4().hex[:8]
    sep = "&" if "?" in UI_URL else "?"
    page = context.new_page()
    page.goto(f"{UI_URL}{sep}workspace={empty_ws}", wait_until="networkidle")
    try:
        expect(page.locator("#main")).to_be_visible()
        expect(page.locator("#empty-state")).to_be_visible(timeout=15_000)
        expect(page.locator("#empty-state")).to_contain_text(
            re.compile(r"no collections yet", re.IGNORECASE)
        )
        # The status line below the form also carries the actionable
        # message so screen readers announce it.
        status = page.locator("#status")
        expect(status).to_contain_text("no collections yet")
        expect(status).to_have_attribute("data-kind", "warn")
        # The collection selector stays at the placeholder.
        expect(page.locator("#collection-select")).to_have_value("")
        # The workspace switcher disclosure is auto-opened so the user
        # can switch without hunting for the toggle.
        expect(page.locator(".ws-switcher")).to_have_attribute("open", "")
    finally:
        page.close()


# ----- M-4: long-answer citations collapse ---------------------------

_FIVE_CITATIONS_PAYLOAD = (
    "{"
    '"status":"answered",'
    '"answer":"See [1] dog adoption, [2] vaccinations, [3] vet, [4] puppy, [5] adoption fee.",'
    '"citations":['
      '{"file_name":"dog-adoption.md","section":"intake","page":1,"score":0.91,"text":"Adoption basics."},'
      '{"file_name":"dog-vaccinations.md","section":"core","page":2,"score":0.84,"text":"Core vaccines."},'
      '{"file_name":"vet-visits.md","section":"schedule","page":1,"score":0.81,"text":"First vet visit."},'
      '{"file_name":"puppy-care.md","section":"week-1","page":1,"score":0.79,"text":"First week at home."},'
      '{"file_name":"adoption-fees.md","section":"pricing","page":1,"score":0.76,"text":"Adoption fees vary."}'
    "]"
    "}"
)


def _intercept_query_with_five_citations(page: Page) -> None:
    """Force /v1/query to return a 5-citation answer regardless of the
    corpus. Lets the M-4 tests assert the collapse behaviour without
    depending on the stub embedding."""
    def _route(route, request):  # type: ignore[no-untyped-def]
        if "/api/v1/query" in request.url:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=_FIVE_CITATIONS_PAYLOAD,
            )
            return
        route.continue_()

    page.route("**/api/v1/query", _route)


def test_long_answer_collapses_overflow_on_desktop(context: BrowserContext) -> None:
    """M-4: on desktop (≥520px), when the answer carries >3 citations,
    the top 3 are expanded and the rest live under a <details> toggle."""
    page = context.new_page()
    page.set_viewport_size({"width": 1280, "height": 800})
    _intercept_query_with_five_citations(page)
    page.goto(UI_URL, wait_until="networkidle")
    cid = _pick_first_collection_value(page)
    page.locator("#collection-select").select_option(cid)
    page.locator("#question").fill("Long answer please.")
    page.locator("#ask").click()
    expect(page.locator("#answer-state")).to_have_attribute(
        "data-state", "answered", timeout=15_000
    )
    items = page.locator("#citations li.citation").count()
    assert items == 5, items
    overflow = page.locator("#citations details.citations-overflow")
    expect(overflow).to_be_visible()
    expect(overflow).not_to_have_attribute("open", "")
    expect(overflow.locator("summary")).to_contain_text(
        re.compile(r"2 more citations\b")
    )
    # The 2 extra citations live inside the overflow <li>s.
    nested = overflow.locator("li.citation").count()
    assert nested == 2, nested
    page.close()


def test_long_answer_collapses_overflow_on_mobile(context: BrowserContext) -> None:
    """M-4: on mobile (≤520px), only the top 1 citation is expanded;
    the rest collapse under <details>."""
    page = context.new_page()
    page.set_viewport_size({"width": 375, "height": 812})
    _intercept_query_with_five_citations(page)
    page.goto(UI_URL, wait_until="networkidle")
    cid = _pick_first_collection_value(page)
    page.locator("#collection-select").select_option(cid)
    page.locator("#question").fill("Long answer please.")
    page.locator("#ask").click()
    expect(page.locator("#answer-state")).to_have_attribute(
        "data-state", "answered", timeout=15_000
    )
    items = page.locator("#citations li.citation")
    assert items.count() == 5
    overflow = page.locator("#citations details.citations-overflow")
    expect(overflow).to_be_visible()
    expect(overflow).not_to_have_attribute("open", "")
    # Mobile threshold: 4 extra citations live under the toggle.
    expect(overflow.locator("summary")).to_contain_text(
        re.compile(r"4 more citations\b")
    )
    page.close()


# ----- M-5 + m-3: hit area and focus outline -----------------------

def test_primary_buttons_meet_44px_hit_area(page: Page) -> None:
    """M-5: every primary button is at least 44 px tall."""
    expect(page.locator("html")).to_have_attribute("data-identity", "ready")
    for sel in ["#ask", "#clear", "#auth-save", "#auth-clear"]:
        loc = page.locator(sel)
        if not loc.is_visible():
            continue
        box = loc.bounding_box()
        assert box is not None, f"no bounding box for {sel}"
        assert box["height"] >= 44, (
            f"{sel} height={box['height']:.1f}px < 44 px (M-5)"
        )


def test_collection_select_meets_44px_hit_area(page: Page) -> None:
    """M-5: the collection selector is at least 44 px tall."""
    expect(page.locator("html")).to_have_attribute("data-identity", "ready")
    page.wait_for_function(
        "document.querySelectorAll('#collection-select option').length >= 1",
        timeout=15_000,
    )
    box = page.locator("#collection-select").bounding_box()
    assert box is not None
    assert box["height"] >= 44, (
        f"#collection-select height={box['height']:.1f}px < 44 px (M-5)"
    )


def test_button_focus_visible_outline(page: Page) -> None:
    """m-3: pressing Tab on a button reveals the styled focus outline.

    The `:focus-visible` pseudo-class only applies for keyboard-induced
    focus. The Ask button is disabled at idle (no question typed), so it
    is not in the Tab order; we use the Clear button which is the first
    enabled focusable button on the page.
    """
    # Move focus to the very top of the page first so the Tab sequence
    # is deterministic.
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.locator("body").focus()
    # Tab through interactive controls until we land on the Clear button.
    for _ in range(30):
        page.keyboard.press("Tab")
        focused_id = page.evaluate("document.activeElement && document.activeElement.id")
        if focused_id == "clear":
            break
    else:
        raise AssertionError("did not reach #clear via Tab navigation")
    style = page.locator("#clear").evaluate(
        "el => { const s = window.getComputedStyle(el);"
        " return { outlineStyle: s.outlineStyle, outlineColor: s.outlineColor, outlineWidth: s.outlineWidth }; }"
    )
    assert style["outlineStyle"] in ("solid", "auto"), style
    # The accent CSS colour is #0284c7 — computed → rgb(2, 132, 199).
    assert "199" in style["outlineColor"] or "2, 132" in style["outlineColor"], (
        style
    )
    assert "2px" in style["outlineWidth"], style
