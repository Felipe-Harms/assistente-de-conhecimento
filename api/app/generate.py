"""Generation pipeline — REQ-004.

Two hard constraints from the contract:
  1. Answers must cite a real chunk (source_id + chunk_id + text snippet).
  2. When the corpus does not support the question, the system must refuse
     explicitly. No fabrication. No "best-guess" partial answers.

We do NOT call an LLM in the main phase. The "answer" is a deterministic
templated summary that names the corpus topics covered by the retrieved
chunks. This is documented in the README and gives a stable, auditable
output that still satisfies the "answer is grounded" requirement.

The refusal envelope is part of the public API contract:
  {"status": "refused", "reason": "insufficient_evidence", "question": "..."}
plus a 200 status code (the refusal is a normal, fully-formed response).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.retrieve import RetrievalResult


REFUSAL_REASON = "insufficient_evidence"


@dataclass
class GroundedAnswer:
    """A non-refusal response. The `answer` field is a deterministic
    concatenation of the top-k chunk snippets separated by ellipses.
    """

    answer: str
    citations: list[dict]


def format_answer(result: RetrievalResult) -> GroundedAnswer:
    """Build a deterministic, traceable answer from the top-k chunks.

    The template is intentionally simple: we list the top chunks with
    their source/page/section so the user can verify every claim. No
    paraphrase, no synthesis — avoiding hallucination is the design
    goal, not eloquence.
    """
    lines = []
    for i, c in enumerate(result.chunks, start=1):
        loc_parts = []
        if c.section:
            loc_parts.append(c.section)
        if c.page is not None:
            loc_parts.append(f"page {c.page}")
        loc = ", ".join(loc_parts) if loc_parts else c.file_name
        lines.append(f"[{i}] {c.file_name} ({loc}): {c.text}")
    answer = "\n".join(lines)
    return GroundedAnswer(answer=answer, citations=[c.to_dict() for c in result.chunks])


__all__ = ["REFUSAL_REASON", "GroundedAnswer", "format_answer"]
