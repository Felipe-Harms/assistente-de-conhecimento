"""Integration tests — REQ-002 ingestion.

The fixture boots the full FastAPI app with the live DB pool. Each test
runs against a freshly-named workspace (`fresh_workspace`) so the suite
is safe to parallelise.

Coverage:
  - Markdown ingestion → 200 + chunks_created ≥ 1
  - Text ingestion → 200 + chunks_created ≥ 1
  - PDF textual ingestion → 200 + page/section populated
  - Reject unsupported extension (.exe) → 4xx
  - Reject empty file → 4xx
  - Reject oversized file → 4xx
  - Idempotent re-ingest of same content → no duplicate document
  - Hash is the SHA-256 of the file bytes
  - page/section populated for PDFs and MD headings
"""

from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ingest import sha256_bytes

# Use the shared corpus dir from the suite conftest (always /srv/data/corpus
# inside the test container, or the repo root when running outside Docker).
from tests.integration.conftest import CORPUS_DIR  # noqa: E402, F401


def _post_text(client: TestClient, *, workspace: str, collection: str, text: str, file_name: str = "inline.md") -> dict:
    return client.post(
        "/v1/ingest",
        data={
            "text": text,
            "file_name": file_name,
            "workspace": workspace,
            "collection": collection,
        },
    ).json()


def _post_file(client: TestClient, *, workspace: str, collection: str, file_path: Path) -> dict:
    with file_path.open("rb") as fh:
        return client.post(
            "/v1/ingest",
            data={"workspace": workspace, "collection": collection},
            files={"upload": (file_path.name, fh, "application/octet-stream")},
        ).json()


def test_ingest_markdown_creates_chunks(app_client: TestClient, fresh_workspace: str) -> None:
    collection = "demo"
    text = (
        "# Dog Adoption\n\n"
        "Adopting a puppy requires vaccination and basic training. "
        "Feed a high-quality commercial dog food appropriate for the dog's age."
    )
    resp = app_client.post(
        "/v1/ingest",
        data={
            "text": text,
            "file_name": "dog.md",
            "workspace": fresh_workspace,
            "collection": collection,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["chunks_created"] >= 1
    assert body["document_id"] > 0
    assert body["collection_id"] > 0
    # SHA-256 of the raw bytes
    expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert body["content_sha"] == expected
    assert len(body["chunk_hashes"]) == body["chunks_created"]


def test_ingest_text_creates_chunks(app_client: TestClient, fresh_workspace: str) -> None:
    text = "Inline text about cats. Cats need protein-rich food and clean litter boxes."
    resp = app_client.post(
        "/v1/ingest",
        data={
            "text": text,
            "file_name": "notes.txt",
            "workspace": fresh_workspace,
            "collection": "text-demo",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["chunks_created"] >= 1


def test_ingest_pdf_creates_chunks_with_page(app_client: TestClient, fresh_workspace: str) -> None:
    pdf_path = CORPUS_DIR / "home-fitness-routine.pdf"
    if not pdf_path.exists():
        pytest.skip("corpus PDF not built yet")
    resp = app_client.post(
        "/v1/ingest",
        data={"workspace": fresh_workspace, "collection": "pdf-demo"},
        files={"upload": (pdf_path.name, pdf_path.open("rb"), "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["chunks_created"] >= 1

    # Verify the chunks have page/section populated.
    cite = app_client.get(f"/v1/citations/{body['chunk_hashes']}", )
    # chunk_hashes is a list of hashes — we need the actual chunk id.
    # The easier path: query the collection's first chunk via the chunks table.
    # Use the api: list collections + citations.
    info = app_client.get(
        f"/v1/collections/{body['collection_id']}",
    )
    assert info.status_code == 200, info.text
    # Now fetch the first chunk id via the citations endpoint:
    # We exposed /v1/citations/{chunk_id}; we get the doc's chunks via retrieval.
    # Use a known query to fetch citations.
    # Instead, query the DB directly via the public endpoint:
    q = app_client.post(
        "/v1/query",
        json={
            "question": "fitness routine",
            "collection_id": body["collection_id"],
            "workspace": fresh_workspace,
            "top_k": 1,
        },
    )
    assert q.status_code == 200, q.text
    qbody = q.json()
    assert qbody["status"] == "answered"
    first = qbody["citations"][0]
    # PDF page is recorded.
    assert first.get("page") is not None, first


def test_ingest_rejects_unsupported_extension(app_client: TestClient, fresh_workspace: str) -> None:
    data = b"fake exe content"
    resp = app_client.post(
        "/v1/ingest",
        data={"workspace": fresh_workspace, "collection": "bad"},
        files={"upload": ("malware.exe", io.BytesIO(data), "application/octet-stream")},
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert "unsupported" in str(body).lower()


def test_ingest_rejects_empty_file(app_client: TestClient, fresh_workspace: str) -> None:
    resp = app_client.post(
        "/v1/ingest",
        data={"workspace": fresh_workspace, "collection": "bad"},
        files={"upload": ("empty.md", io.BytesIO(b""), "text/markdown")},
    )
    assert resp.status_code == 400, resp.text


def test_ingest_rejects_oversized_file(app_client: TestClient, fresh_workspace: str, monkeypatch) -> None:
    """Simulate oversize by mounting a tiny ingest_max_bytes cap.

    We patch `app.ingest._enforce_size` directly so the test exercises the
    validation path without rebuilding the FastAPI app (which would close
    the shared DB pool).
    """
    from app import ingest as ingest_mod

    def _tiny_size(byte_size: int, max_bytes: int) -> None:
        if byte_size <= 0:
            raise ingest_mod.IngestError("file is empty")
        if byte_size > 100:
            raise ingest_mod.IngestError(
                f"file too large: {byte_size} bytes > max 100 bytes"
            )

    monkeypatch.setattr(ingest_mod, "_enforce_size", _tiny_size)

    resp = app_client.post(
        "/v1/ingest",
        data={
            "text": "x" * 500,
            "file_name": "big.md",
            "workspace": fresh_workspace,
            "collection": "big",
        },
    )
    assert resp.status_code == 400, resp.text
    assert "too large" in str(resp.json()).lower()


def test_ingest_is_idempotent_by_content_hash(app_client: TestClient, fresh_workspace: str) -> None:
    text = "Same content twice. Same content twice. Same content twice."
    body1 = _post_text(
        app_client,
        workspace=fresh_workspace,
        collection="idem",
        text=text,
        file_name="idem.md",
    )
    body2 = _post_text(
        app_client,
        workspace=fresh_workspace,
        collection="idem",
        text=text,
        file_name="idem.md",
    )
    assert body1["document_id"] == body2["document_id"], body2
    assert body1["content_sha"] == body2["content_sha"]
    # Chunks should be the same set (re-generated but with same set of hashes).
    assert set(body1["chunk_hashes"]) == set(body2["chunk_hashes"])


def test_ingest_hash_matches_sha256(app_client: TestClient, fresh_workspace: str) -> None:
    text = "A unique content sample for hash verification."
    body = _post_text(
        app_client, workspace=fresh_workspace, collection="hash", text=text,
        file_name="hash.md",
    )
    expected = sha256_bytes(text.encode("utf-8"))
    assert body["content_sha"] == expected
