"""REQ-005 / P0 acceptance — 12-question demo suite.

The product contract for the P0 demo is:

  - 12 questions (8 positive, 4 negative) hit the corpus.
  - Every positive question is answered, with every returned citation
    clearing the per-citation relevance filter (zero irrelevant
    citations).
  - Every negative (off-corpus) question is refused explicitly with
    ``insufficient_evidence``.

This test ingests the demo corpus shipped under ``data/corpus/`` and
exercises the same question set as the production proof runner
(``scripts/run_proof.py`` + ``proof/questions.json``) but from inside
the test container, so a fresh ``docker compose run --rm test pytest
tests/acceptance/test_demo_12.py`` is enough to verify the contract —
no separate proof build step required.

Setting ``RETRIEVAL_MIN_SCORE`` to a tuned value for the demo suite is
the responsibility of the deployment; this test uses the configured
threshold and asserts every returned citation clears it.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

# Question set is canonically hosted in proof/questions.json — this is
# the same fixture the production proof runner reads, so the
# acceptance contract is checked in lockstep with the proof cycle.
#
# Path resolution handles two layouts:
#   - host / runner-side pytest: parents[2] is the repo root, so
#     proof/ resolves there (CI step 11 runs pytest directly).
#   - test container (docker compose run --rm test pytest): parents[2]
#     is /srv, but the test image stages the repo at /srv/repo, so
#     proof/ is volume-mounted at /srv/repo/proof rather than baked in.
_QUESTIONS_CANDIDATES = (
    Path(__file__).resolve().parents[2] / "proof" / "questions.json",
    Path("/srv/repo/proof/questions.json"),
)
QUESTIONS_PATH = next(
    (p for p in _QUESTIONS_CANDIDATES if p.exists()), _QUESTIONS_CANDIDATES[0]
)
CORPUS_DIR = Path(__file__).resolve().parents[2] / "data" / "corpus"


_MIME = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".pdf": "application/pdf",
}


def _ingest_corpus(client: TestClient, workspace: str, collection: str) -> int:
    """Ingest every supported file under the demo corpus directory.

    Returns the resolved ``collection_id`` so the query loop can target
    every chunk in a single collection.
    """
    collection_id: int | None = None
    for path in sorted(CORPUS_DIR.iterdir()):
        if path.suffix.lower() not in _MIME:
            continue
        with path.open("rb") as fh:
            resp = client.post(
                "/v1/ingest",
                data={"workspace": workspace, "collection": collection},
                files={"upload": (path.name, fh, _MIME[path.suffix.lower()])},
            )
        assert resp.status_code == 200, (
            f"ingest failed for {path.name}: {resp.status_code} {resp.text}"
        )
        body = resp.json()
        # The first ingest call is authoritative for collection_id —
        # subsequent upserts keep the same id, but always capture the
        # latest to be safe.
        collection_id = body["collection_id"]
        assert body["chunks_created"] >= 1, path
    assert collection_id is not None, "no supported corpus files ingested"
    return collection_id


def _load_questions() -> list[dict]:
    payload = json.loads(QUESTIONS_PATH.read_text())
    qs = payload["questions"]
    meta = payload["metadata"]
    assert "expected_question_count_min" in meta
    lo, hi = meta["expected_question_count_min"], meta["expected_question_count_max"]
    assert lo <= len(qs) <= hi, (
        f"questions.json outside REQ-005 bounds: {len(qs)} not in [{lo}, {hi}]"
    )
    pos = sum(1 for q in qs if q.get("category") == "positive")
    neg = sum(1 for q in qs if q.get("category") == "negative")
    assert pos >= meta["expected_positive_min"]
    assert neg >= meta["expected_negative_min"]
    return qs


def test_demo_12_questions_full_acceptance(
    app_client: TestClient, fresh_workspace: str
) -> None:
    """Drive the 12-question suite through the API and assert every
    contract:
      - ``status`` matches ``expected_status`` for every question.
      - For positive questions the answer is non-empty AND every
        returned citation's score clears the per-citation threshold
        AND at least one citation's text contains an expected topic
        keyword.
      - For negative questions ``reason == 'insufficient_evidence'``,
        ``citations == []``, and no answer field is populated.
    """
    collection_id = _ingest_corpus(app_client, fresh_workspace, "demo12")
    questions = _load_questions()
    assert len(questions) == 12, (
        f"demo contract is 12 questions; questions.json has {len(questions)}"
    )

    pos_ok = 0
    neg_ok = 0
    failures: list[str] = []

    for q in questions:
        resp = app_client.post(
            "/v1/query",
            json={
                "question": q["question"],
                "collection_id": collection_id,
                "workspace": fresh_workspace,
                "top_k": 5,
            },
        )
        assert resp.status_code == 200, q
        body = resp.json()

        expected = q["expected_status"]
        actual = body.get("status")
        if expected == "answered":
            if actual != "answered":
                failures.append(
                    f"{q['id']} expected answered got {actual} (refused: "
                    f"reason={body.get('reason')!r}, best={body.get('best_score')})"
                )
                continue
            answer = (body.get("answer") or "").strip()
            assert answer, f"{q['id']} answered without answer text: {body}"
            citations = body.get("citations") or []
            assert citations, f"{q['id']} answered without citations: {body}"
            threshold = body.get("threshold")
            assert threshold is not None, body
            for cite in citations:
                score = cite.get("score", 0.0)
                assert score >= threshold, (
                    f"{q['id']} citation clears threshold check: "
                    f"score={score} < threshold={threshold} cite={cite!r}"
                )
            # Topic-keyword hit — at least one expected keyword must
            # appear in either the answer or the cited chunk text.
            keywords = q.get("expected_topic_keywords") or []
            if keywords:
                haystack = (answer + "\n" + " ".join(c["text"] for c in citations)).lower()
                if not any(k.lower() in haystack for k in keywords):
                    failures.append(
                        f"{q['id']} keyword miss: expected any of "
                        f"{keywords} got none in answer/citations"
                    )
                    continue
            pos_ok += 1
        else:  # negative
            if actual != "refused":
                failures.append(
                    f"{q['id']} expected refused got {actual} answer={body.get('answer')!r}"
                )
                continue
            assert body.get("reason") == "insufficient_evidence", body
            assert body.get("citations") == [], body
            assert body.get("answer") in (None, ""), body
            neg_ok += 1

    assert pos_ok == 8, (
        f"positive: {pos_ok}/8 matched — failures={failures!r}"
    )
    assert neg_ok == 4, (
        f"negative: {neg_ok}/4 matched — failures={failures!r}"
    )
    assert pos_ok + neg_ok == 12, (
        f"demo contract 12/12 failed: {pos_ok}+{neg_ok} failures={failures!r}"
    )
