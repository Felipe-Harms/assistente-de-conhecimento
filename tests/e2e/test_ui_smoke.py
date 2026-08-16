"""E2E — REQ-006 smoke: page loads, identity wired, scope visible."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


def test_page_renders_with_default_identity(page: Page) -> None:
    """Static UI loads and renders the configured brand from /v1/identity."""
    expect(page).to_have_title("Assistente de Conhecimento")
    expect(page.locator("#brand-name")).to_have_text("Assistente de Conhecimento")
    expect(page.locator("#subtitle")).to_be_visible()
    expect(page.locator("#footer-note")).to_be_visible()
    # The `data-identity` attribute is set after the JSON round-trip
    # completes — a strong signal that the JS actually fetched /api/v1/identity.
    expect(page.locator("html")).to_have_attribute("data-identity", "ready")
    expect(page.locator("html")).to_have_attribute("data-ui", "ready")


def test_auth_pill_visible_with_disabled_state(page: Page) -> None:
    """Default AUTH_ENABLED=false → pill is muted and panel is hidden."""
    pill = page.locator("#auth-pill")
    expect(pill).to_be_visible()
    expect(pill).to_have_text("Auth disabled")
    expect(pill).to_have_class(__import__("re").compile(r"pill-muted"))
    # The bearer-token input is hidden when auth is off.
    expect(page.locator("#auth-panel")).to_be_hidden()


def test_collection_selector_populated(page: Page) -> None:
    """`/v1/collections` is fetched; the selector is populated."""
    # Wait for the placeholder text to disappear and at least one option
    # with a numeric value (= a real collection id) to appear. The
    # default seed is present after seeding, so we
    # also accept an empty-collections state but assert the JS
    # round-tripped either way.
    page.wait_for_function(
        "!document.querySelector('#collection-select option[value=\"\"]') || "
        "document.querySelectorAll('#collection-select option[value]:not([value=\"\"])').length >= 1",
        timeout=15_000,
    )
    options = page.locator("#collection-select option").all_inner_texts()
    # Either a real collection is shown, or the explicit 'no collections'
    # marker is rendered — both prove the JS hit the API.
    assert options, "collection select rendered no options"
    assert any(
        o.strip().startswith(("—", "no ")) or o.strip() for o in options
    ), options


def test_scope_and_limits_panel_present(page: Page) -> None:
    expect(page.locator("h2#limits-title")).to_be_visible()
    bullets = page.locator("ul.limits li").all_inner_texts()
    assert len(bullets) >= 3, bullets
    assert any("OCR" in b for b in bullets)


def test_ask_button_disabled_until_input(page: Page) -> None:
    """The submit button stays disabled until both inputs are valid."""
    ask = page.locator("#ask")
    expect(ask).to_be_disabled()
    # Wait for the JS round-trip so a real option (if any) is rendered.
    page.wait_for_function(
        "!document.querySelector('#collection-select option[value=\"\"]') || "
        "document.querySelectorAll('#collection-select option[value]:not([value=\"\"])').length >= 1",
        timeout=15_000,
    )
    # Find the first option whose value is non-empty by reading the
    # rendered options and selecting by value via Playwright's select
    # helper (which works on closed select widgets).
    values = page.evaluate(
        "Array.from(document.querySelectorAll('#collection-select option'))"
        ".map(o => o.value).filter(v => v)"
    )
    picked = False
    if values:
        page.locator("#collection-select").select_option(values[0])
        picked = True
    # Without a question, still disabled (only when we have a collection).
    if picked:
        expect(ask).to_be_disabled()
        page.locator("#question").fill("What is in the corpus?")
        expect(ask).to_be_enabled()
    else:
        # No collections exist in this workspace — the button stays
        # disabled because there is nothing to query.
        page.locator("#question").fill("What is in the corpus?")
        expect(ask).to_be_disabled()