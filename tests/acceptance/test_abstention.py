"""Acceptance tests — REQ-004 abstention (refusal).

Hard guarantees:
  - status == "refused"
  - reason == "insufficient_evidence"
  - citations == []
  - The `answer` answer field is null / absent.
  - The response body never contains fabricated text that hints at a
    real answer.
  - /v1/citations/{chunk_id} for any chunk_id from a refused response
    must be either absent or genuinely present and unaltered.
"""

from __future__ import annotations

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


def test_offscreen_question_is_refused(app_client: TestClient, fresh_workspace: str) -> None:
    body = _ingest(
        app_client,
        workspace=fresh_workspace,
        collection="refuse",
        text=(
            "# Dog Adoption Guide\n\n"
            "Adopting a puppy requires vaccination and basic training. "
            "Feed a high-quality commercial dog food appropriate for the dog's age."
        ),
        file_name="dog.md",
    )
    # Off-topic: completely unrelated science question.
    q = app_client.post(
        "/v1/query",
        json={
            "question": "What is the speed of light in a vacuum?",
            "collection_id": body["collection_id"],
            "workspace": fresh_workspace,
        },
    )
    assert q.status_code == 200, q.text
    qbody = q.json()
    assert qbody["status"] == "refused", qbody
    assert qbody["reason"] == "insufficient_evidence"
    assert qbody["citations"] == []
    assert qbody.get("answer") in (None, "")


def test_empty_collection_refuses(app_client: TestClient, fresh_workspace: str) -> None:
    create = app_client.post(
        "/v1/collections",
        json={"name": "empty-refuse", "workspace": fresh_workspace},
    )
    assert create.status_code == 201, create.text
    cid = create.json()["id"]
    q = app_client.post(
        "/v1/query",
        json={
            "question": "Anything at all?",
            "collection_id": cid,
            "workspace": fresh_workspace,
        },
    )
    assert q.status_code == 200, q.text
    qbody = q.json()
    assert qbody["status"] == "refused"
    assert qbody["reason"] == "insufficient_evidence"
    assert qbody["citations"] == []


def test_nonexistent_collection_refuses(app_client: TestClient, fresh_workspace: str) -> None:
    q = app_client.post(
        "/v1/query",
        json={
            "question": "Anything?",
            "collection_id": 999_999,
            "workspace": fresh_workspace,
        },
    )
    assert q.status_code == 200, q.text
    qbody = q.json()
    assert qbody["status"] == "refused"
    assert qbody["reason"] == "insufficient_evidence"
    assert qbody["citations"] == []


def test_refusal_response_does_not_leak_chunk_text(
    app_client: TestClient, fresh_workspace: str
) -> None:
    """A refused response must not echo any corpus content as a fake answer."""
    body = _ingest(
        app_client,
        workspace=fresh_workspace,
        collection="leak",
        text=(
            "SECRET_TOKEN_PYTHONIC_UNICORN_42. "
            "This is a unique marker that should never appear in a refusal."
        ),
        file_name="leak.md",
    )
    q = app_client.post(
        "/v1/query",
        json={
            "question": "What is the meaning of life, the universe, and everything?",
            "collection_id": body["collection_id"],
            "workspace": fresh_workspace,
        },
    )
    assert q.status_code == 200, q.text
    qbody = q.json()
    assert qbody["status"] == "refused"
    raw = str(qbody)
    assert "SECRET_TOKEN_PYTHONIC_UNICORN_42" not in raw
    assert qbody["answer"] in (None, "")


def test_threshold_decision_is_documented(app_client: TestClient, fresh_workspace: str) -> None:
    """The response payload should expose best_score and threshold so the
    operator can audit the refusal decision."""
    body = _ingest(
        app_client,
        workspace=fresh_workspace,
        collection="audit",
        text="Totally unrelated topic about concrete poetry and type theory.",
        file_name="audit.md",
    )
    q = app_client.post(
        "/v1/query",
        json={
            "question": "What is the meaning of life?",
            "collection_id": body["collection_id"],
            "workspace": fresh_workspace,
        },
    )
    assert q.status_code == 200, q.text
    qbody = q.json()
    assert qbody["status"] == "refused"
    assert "best_score" in qbody
    assert "threshold" in qbody
    assert qbody["best_score"] < qbody["threshold"]
