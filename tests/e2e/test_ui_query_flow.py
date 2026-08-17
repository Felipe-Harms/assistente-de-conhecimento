"""E2E — REQ-006 query flow: happy path (answered + citations) and
refusal path (insufficient_evidence banner).

Each test seeds a fresh workspace with the synthetic corpus so we have
predictable on-topic questions and clearly out-of-domain ones to refuse.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect


@pytest.fixture
def populated_page(page_in_workspace, ingested_corpus, context) -> Page:
    """Boot the UI pinned to the test workspace; pre-select its collection."""
    page = page_in_workspace(ingested_corpus["workspace_id"])
    # Wait for the identity round-trip and the collections list.
    expect(page.locator("html")).to_have_attribute("data-identity", "ready")
    page.wait_for_function(
        "!document.querySelector('#collection-select option[value=\"\"]') || "
        "document.querySelectorAll('#collection-select option[value]:not([value=\"\"])').length >= 1",
        timeout=15_000,
    )
    # Pick the first non-placeholder option by value (select_option
    # works on closed select widgets).
    values = page.evaluate(
        "Array.from(document.querySelectorAll('#collection-select option'))"
        ".map(o => o.value).filter(v => v)"
    )
    if values:
        page.locator("#collection-select").select_option(values[0])
    yield page
    page.close()
    context.close()


def test_happy_path_answered_with_citations(populated_page: Page) -> None:
    """On-topic question → `answered` state + ≥1 citation rendered."""
    populated_page.locator("#question").fill(
        "What core vaccinations does a newly adopted dog need?"
    )
    populated_page.locator("#ask").click()

    # Wait for the answer state to flip from 'idle' to 'answered'.
    expect(populated_page.locator("#answer-state")).to_have_attribute(
        "data-state", "answered", timeout=15_000
    )

    citations = populated_page.locator("#citations li.citation")
    expect(populated_page.locator("#citations")).to_be_visible()
    count = citations.count()
    assert count >= 1, f"expected ≥1 citation, got {count}"

    # Each citation shows file + score + a snippet.
    first = citations.first
    expect(first.locator(".citation-file")).to_be_visible()
    expect(first.locator(".citation-score")).to_be_visible()
    expect(first.locator(".citation-body")).to_be_visible()

    # The status line reports success.
    status = populated_page.locator("#status")
    expect(status).to_have_text(re.compile(r"Answered with \d+ citation"))


def test_refusal_path_shows_insufficient_evidence_banner(populated_page: Page) -> None:
    """Off-topic question → `refused` state with explicit reason banner."""
    populated_page.locator("#question").fill(
        "What is the speed of light in a vacuum in metres per second?"
    )
    populated_page.locator("#ask").click()

    expect(populated_page.locator("#answer-state")).to_have_attribute(
        "data-state", "refused", timeout=15_000
    )

    # The answer container carries the explicit "no answer" copy and
    # the structured `reason=insufficient_evidence` field.
    answer_text = populated_page.locator("#answer").inner_text()
    assert "no answer" in answer_text.lower(), answer_text
    assert "insufficient_evidence" in answer_text, answer_text

    # No citations rendered on the refusal path.
    expect(populated_page.locator("#citations")).to_be_hidden()

    # Status reflects the refusal.
    expect(populated_page.locator("#status")).to_contain_text("Refused")


def test_keyboard_shortcut_submits(populated_page: Page) -> None:
    """Ctrl+Enter submits the question from the textarea."""
    populated_page.locator("#question").fill("How do I license my open-source project?")
    populated_page.locator("#question").press("Control+Enter")
    expect(populated_page.locator("#answer-state")).to_have_attribute(
        "data-state", "answered", timeout=15_000
    )


def test_clear_button_resets_state(populated_page: Page) -> None:
    populated_page.locator("#question").fill("What core vaccinations does a newly adopted dog need?")
    populated_page.locator("#ask").click()
    expect(populated_page.locator("#answer-state")).to_have_attribute(
        "data-state", "answered", timeout=15_000
    )
    populated_page.locator("#clear").click()
    expect(populated_page.locator("#answer-state")).to_have_attribute("data-state", "idle")
    expect(populated_page.locator("#question")).to_have_value("")