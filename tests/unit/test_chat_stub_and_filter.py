"""Unit tests for the chat client + per-citation relevance filter.

These run in-process without a database. They pin the contract that
``StubChatClient`` produces a short, grounded answer (no fabrication)
and that ``filter_relevant`` drops citations strictly below the
configured threshold.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.chat import REFUSAL_TOKEN, StubChatClient
from app.generate import filter_relevant
from app.retrieve import Citation, RetrievalResult


def _cite(score: float, text: str = "snippet") -> Citation:
    return Citation(
        chunk_id=1,
        document_id=1,
        source="s",
        file_name="f.md",
        page=None,
        section=None,
        score=score,
        text=text,
    )


def test_filter_relevant_drops_citations_below_threshold() -> None:
    cites = [_cite(0.50, "top"), _cite(0.18, "near miss"), _cite(0.05, "garbage")]
    kept = filter_relevant(cites, 0.20)
    assert len(kept) == 1
    assert kept[0].score == 0.50


def test_filter_relevant_keeps_ordering() -> None:
    cites = [_cite(0.30), _cite(0.50), _cite(0.40)]
    kept = filter_relevant(cites, 0.20)
    assert [c.score for c in kept] == [0.30, 0.50, 0.40]


def test_filter_relevant_empty_when_all_below() -> None:
    cites = [_cite(0.10), _cite(0.05)]
    assert filter_relevant(cites, 0.20) == []


def test_filter_relevant_drops_citations_without_token_overlap() -> None:
    """Off-corpus questions that ride a SHA-256 hash-collision cosine
    must be refused: ``mongolia`` and ``fermentation`` hash to the
    same ridge in the stub embedder, so the cosine alone clears the
    threshold. The overlap gate is what keeps ``What is the capital
    of Mongolia?`` out of an answer built on a fermentation chunk.
    """
    cite = _cite(
        0.50,
        "Fermentation Time Most vegetable ferments are ready in 5 to 14 days at "
        "room temperature.",
    )
    kept = filter_relevant(
        [cite], 0.20, question="What is the capital of Mongolia?"
    )
    assert kept == []


def test_filter_relevant_keeps_citation_with_shared_token() -> None:
    cite = _cite(
        0.50,
        "Feeding your cat obligate carnivore Cats need protein-rich wet food.",
    )
    kept = filter_relevant(
        [cite], 0.20, question="How should I feed my cat?"
    )
    assert len(kept) == 1
    assert kept[0].score == 0.50


def test_filter_relevant_question_none_skips_overlap_gate() -> None:
    """Legacy callers that pass ``question=None`` get the original
    cosine-only behaviour — no overlap gate."""
    cite = _cite(0.50, "anything")
    kept = filter_relevant([cite], 0.20)
    assert len(kept) == 1


def test_stub_chat_returns_insufficient_evidence_when_no_citations() -> None:
    client = StubChatClient()
    out = asyncio.run(client.complete("anything", []))
    assert out == REFUSAL_TOKEN


def test_stub_chat_returns_short_grounded_answer() -> None:
    client = StubChatClient()
    cite = _cite(0.50, "Cats are obligate carnivores and need protein.")
    out = asyncio.run(client.complete("How should I feed my cat?", [cite]))
    # The answer must be short, contain chunk text, and reference [1].
    assert "Cats are obligate carnivores" in out
    assert "[1]" in out
    assert len(out.split()) < 60


def test_stub_chat_does_not_fabricate_above_citation() -> None:
    client = StubChatClient()
    cite = _cite(0.50, "Only one short sentence in this chunk.")
    out = asyncio.run(client.complete("?", [cite]))
    # Must NOT contain content beyond the chunk + citation pointer.
    assert "Only one short sentence" in out
    forbidden = "turtles", "kubernetes", "wikipedia"
    for word in forbidden:
        assert word not in out.lower()
