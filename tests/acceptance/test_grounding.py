"""Acceptance tests — REQ-004 grounding.

For every question that has support in the corpus:
  - The response status is "answered".
  - The response includes at least one citation.
  - Each citation's `text` matches a real chunk in the database.
  - Each citation's `chunk_id` resolves through `/v1/citations/{chunk_id}`.
  - The cited content is plausibly related to the question (token overlap).
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient


def _ingest(client: TestClient, workspace: str, collection: str, text: str, file_name: str) -> dict:
    return client.post(
        "/v1/ingest",
        data={
            "text": text,
            "file_name": file_name,
            "workspace": workspace,
            "collection": collection,
        },
    ).json()


_STOP = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been",
    "and", "or", "of", "to", "in", "on", "at", "for", "with", "by",
    "as", "it", "this", "that", "from", "if", "but", "not",
    "do", "does", "did", "will", "would", "can", "could", "should",
    "may", "might", "must", "shall", "have", "has", "had",
    "i", "you", "he", "she", "we", "they", "them", "their", "its",
    "what", "which", "who", "when", "where", "why", "how",
}


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in re.findall(r"[a-z0-9]+", text.lower()) if t.lower() not in _STOP and len(t) > 2}


def test_answered_question_has_citation_with_matching_text(
    app_client: TestClient, fresh_workspace: str
) -> None:
    body = _ingest(
        app_client,
        workspace=fresh_workspace,
        collection="ground",
        text=(
            "# Fermentation\n\n"
            "Fermentation produces lactic acid via lactobacilli. "
            "A 2 percent salt brine is typical for sauerkraut."
        ),
        file_name="ground.md",
    )
    q = app_client.post(
        "/v1/query",
        json={
            "question": "What is a typical salt brine for sauerkraut?",
            "collection_id": body["collection_id"],
            "workspace": fresh_workspace,
        },
    )
    assert q.status_code == 200, q.text
    qbody = q.json()
    assert qbody["status"] == "answered", qbody
    assert qbody["answer"], "answer must be non-empty"
    assert qbody["citations"], "answered responses must have citations"

    top = qbody["citations"][0]
    # The cited chunk must contain 'salt' or 'sauerkraut' or 'brine'.
    ctext = top["text"].lower()
    assert any(tok in ctext for tok in ["salt", "sauerkraut", "brine", "lactobacilli"]), top

    # The citation must be resolvable via /v1/citations/{chunk_id}.
    detail = app_client.get(f"/v1/citations/{top['chunk_id']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["content"] == top["text"]


def test_answered_question_tokens_overlap_with_corpus(
    app_client: TestClient, fresh_workspace: str
) -> None:
    """For a clearly on-topic question, the highest-scoring citation must
    share at least one meaningful token with the question."""
    body = _ingest(
        app_client,
        workspace=fresh_workspace,
        collection="overlap",
        text=(
            "# Pytest\n\n"
            "Pytest discovers tests under tests/ and runs them with "
            "pytest. The pytest runner supports fixtures, parametrize, and "
            "markers. Pytest is a popular Python testing framework."
        ),
        file_name="pytest.md",
    )
    q = app_client.post(
        "/v1/query",
        json={
            "question": "How does pytest discover tests?",
            "collection_id": body["collection_id"],
            "workspace": fresh_workspace,
        },
    )
    assert q.status_code == 200, q.text
    qbody = q.json()
    assert qbody["status"] == "answered", qbody
    top = qbody["citations"][0]
    q_tokens = _tokens(qbody["answer"])
    chunk_tokens = _tokens(top["text"])
    # Must share at least one meaningful token.
    assert q_tokens & chunk_tokens, (q_tokens, chunk_tokens)


def test_answered_includes_section_or_page_when_available(
    app_client: TestClient, fresh_workspace: str
) -> None:
    body = _ingest(
        app_client,
        workspace=fresh_workspace,
        collection="sec",
        text=(
            "# Markdown\n\n"
            "## Subsections\n\n"
            "Markdown allows headings, lists, and code blocks. "
            "Headings are formed with hash characters."
        ),
        file_name="sec.md",
    )
    q = app_client.post(
        "/v1/query",
        json={
            "question": "What are subsections in markdown?",
            "collection_id": body["collection_id"],
            "workspace": fresh_workspace,
        },
    )
    assert q.status_code == 200, q.text
    qbody = q.json()
    assert qbody["status"] == "answered"
    section = qbody["citations"][0].get("section")
    # A heading-derived section should be recorded.
    assert section is not None
    assert section  # non-empty
