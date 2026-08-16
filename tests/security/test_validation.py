"""Security smoke tests — REQ-007: input validation baseline."""

from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def embed_url() -> str:
    return "/v1/embeddings"


def test_embedding_rejects_empty_input(api_client, embed_url: str) -> None:
    resp = api_client.post(embed_url, json={"input": []})
    assert resp.status_code == 422, resp.text


def test_embedding_rejects_empty_string(api_client, embed_url: str) -> None:
    resp = api_client.post(embed_url, json={"input": [""]})
    assert resp.status_code == 422, resp.text


def test_embedding_rejects_nul_byte(api_client, embed_url: str) -> None:
    resp = api_client.post(embed_url, json={"input": ["hello\x00world"]})
    assert resp.status_code == 422, resp.text


def test_embedding_rejects_oversize(api_client, embed_url: str) -> None:
    resp = api_client.post(embed_url, json={"input": ["x" * 5000]})
    assert resp.status_code == 422, resp.text


def test_embedding_rejects_extra_fields(api_client, embed_url: str) -> None:
    """Pydantic with `extra='forbid'` rejects surprise fields."""
    resp = api_client.post(embed_url, json={"input": ["ok"], "rogue": "x"})
    assert resp.status_code == 422, resp.text


def test_embedding_accepts_minimal_valid(api_client, embed_url: str) -> None:
    resp = api_client.post(embed_url, json={"input": ["ok"]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dim"] >= 16
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 1
    assert len(body["data"][0]) == body["dim"]
