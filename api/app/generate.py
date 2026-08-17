"""Grounded answer generation pipeline (REQ-004).

Hard contract:

  1. Answers must cite a real chunk (source_id + chunk_id + text snippet).
  2. When no relevance-filtered citation exists, the system refuses
     explicitly with ``insufficient_evidence``. No fabrication. No
     best-guess partial answers.
  3. The chat model never sees anything except the relevance-filtered
     passages retrieved for the question. If it returns the literal
     token ``INSUFFICIENT_EVIDENCE`` (or returns nothing), the envelope
     is still a refusal — chat refusal is a soft signal, not an
     authorisation to invent.

Two building blocks:

  - ``filter_relevant`` — drops every chunk below the configured
    per-citation threshold. Returned list is what the chat client sees
    and what the response envelope lists under ``citations``.

  - ``generate`` — async wrapper that asks the chat client to summarise
    the filtered citations. Returns ``GroundedAnswer`` or ``None`` to
    signal a refusal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.chat import REFUSAL_TOKEN, ChatClient
from app.embeddings import _tokenize
from app.retrieve import Citation, RetrievalResult

REFUSAL_REASON = "insufficient_evidence"


@dataclass
class GroundedAnswer:
    """A non-refusal response. The ``answer`` field is a short, citation-
    backed summary produced by the chat client. ``citations`` is the
    relevance-filtered subset of chunks that informed the answer."""

    answer: str
    citations: list[dict]


def filter_relevant(
    citations: Sequence[Citation],
    threshold: float,
    *,
    question: str | None = None,
    token_overlap: bool = True,
) -> list[Citation]:
    """Per-citation relevance filter.

    Drops every chunk whose cosine score is strictly below
    ``threshold``. The returned list preserves the original cosine
    ordering so the top chunk is still index 0.

    When ``question`` is supplied AND ``token_overlap=True`` (the
    default), the filter applies a second gate: every surviving
    citation must share at least one non-trivial token
    (post-stopword, post-length) with the question. This catches
    SHA-256 hash-collision false positives produced by the local
    deterministic stub where two unrelated tokens map to the same
    ridge — e.g. ``mongolia`` and ``fermentation`` both hashing to
    idx 533 with sign +1, producing cosine 0.50 between ``What is
    the capital of Mongolia?`` and a ``Fermentation Time`` chunk
    despite zero real vocabulary overlap. Without this gate the
    cosine-only filter passes such collisions and the system
    answers an off-corpus question with garbage from an unrelated
    chunk.

    With live OpenAI-compatible embeddings the cosine signal is
    strong enough that the token overlap gate becomes a liability
    (real embeddings push on-topic well above the threshold with
    no false positives and overlap can drop legitimate chunks when
    the question uses paraphrased vocabulary). Callers that wire
    ``EMBEDDING_STUB=false`` must pass ``token_overlap=False`` so
    the cosine filter is the only gate. ``question=None`` skips
    the overlap gate regardless of ``token_overlap`` (legacy
    callers).
    """
    kept = [c for c in citations if c.score >= threshold]
    if question is not None and token_overlap:
        q_tokens = frozenset(_tokenize(question))
        kept = [c for c in kept if q_tokens & frozenset(_tokenize(c.text))]
    return kept


async def generate(
    *,
    chat: ChatClient,
    question: str,
    citations: Sequence[Citation],
    threshold: float,
) -> GroundedAnswer | None:
    """Build a grounded answer or signal a refusal.

    Returns ``None`` when there is no answer to give — either no
    citations clear the threshold or the chat client reported the
    ``INSUFFICIENT_EVIDENCE`` token. Callers translate ``None`` into
    the public refusal envelope.

    The chat client is invoked with the relevance-filtered citation
    list so the model cannot see chunks that failed the relevance gate.
    """
    relevant = filter_relevant(citations, threshold)
    if not relevant:
        return None
    text = await chat.complete(question, list(relevant))
    text = (text or "").strip()
    if not text:
        return None
    # The chat client surfaces a refusal by emitting the literal refusal
    # token verbatim (including casing). Anything starting with the
    # token (after the strip above) means "context was insufficient".
    if text.upper().startswith(REFUSAL_TOKEN):
        return None
    return GroundedAnswer(answer=text, citations=[c.to_dict() for c in relevant])


def filter_result(result: RetrievalResult, threshold: float) -> RetrievalResult:
    """Construct a new ``RetrievalResult`` whose chunks are filtered.

    Convenience helper used by the API route to keep ``best_score``
    consistent with the filtered citation list: after dropping chunks,
    ``best_score`` is recomputed from whatever survived (or 0.0 if the
    list is empty).
    """
    kept = filter_relevant(result.chunks, threshold)
    best = kept[0].score if kept else 0.0
    return RetrievalResult(chunks=kept, best_score=best)


__all__ = [
    "REFUSAL_REASON",
    "GroundedAnswer",
    "filter_relevant",
    "filter_result",
    "generate",
]
