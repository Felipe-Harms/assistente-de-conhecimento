"""Unit tests for the live HTTP adapters (embeddings + chat).

These tests pin the contract of ``HttpEmbeddingClient`` and
``HttpChatClient`` against ``httpx.MockTransport`` so the suite has no
network requirement. They cover:

  a) URL construction (no string-concat bugs, trailing-slash tolerant).
  b) ``Authorization: Bearer <KEY>`` header is sent.
  c) Request body matches the schema documented in the client.
  d) 200 response is parsed into a list of vectors / a single string.
  e) 4xx/5xx responses raise the typed exception (not a generic crash).
  f) Embedding dimension mismatch raises the typed exception.

Tests run as plain ``def`` functions so they execute inside the
shipped test image without ``pytest-asyncio``. Each ``_run`` helper
wraps an ``asyncio.run`` call around the body of an adapter coroutine.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from app.chat import ChatError, HttpChatClient
from app.embeddings import EmbeddingError, HttpEmbeddingClient
from app.retrieve import Citation


def _cite(text: str = "grounded source text") -> Citation:
    """Return a Citation that exercises the HTTP path.

    ``HttpChatClient.complete`` short-circuits with ``REFUSAL_TOKEN`` when
    ``citations`` is empty, so the mock transport would never fire.
    Tests that pin the HTTP wiring always pass at least one Citation
    so the request reaches the network layer.
    """
    return Citation(
        chunk_id=1,
        document_id=1,
        source="s",
        file_name="f.md",
        page=None,
        section=None,
        score=0.50,
        text=text,
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _run(coro):
    """Drive an async coroutine from a sync test function."""
    return asyncio.run(coro)


def _json_response(status: int, payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(status, json=payload)


def _make_embedding_client(
    handler,
    *,
    base_url: str = "https://api.openai.com/v1",
    api_key: str = "sk-test-key-abc123",
    model: str = "text-embedding-3-small",
    dim: int = 3,
) -> HttpEmbeddingClient:
    """Build an ``HttpEmbeddingClient`` with a mocked transport."""
    client = HttpEmbeddingClient(
        base_url=base_url,
        api_key=api_key,
        model=model,
        dim=dim,
        timeout_s=5.0,
    )
    client._client = httpx.AsyncClient(
        timeout=5.0, transport=httpx.MockTransport(handler)
    )
    return client


def _make_chat_client(
    handler,
    *,
    base_url: str = "https://api.openai.com/v1",
    api_key: str = "sk-test-key-abc123",
    model: str = "gpt-4o-mini",
) -> HttpChatClient:
    """Build an ``HttpChatClient`` with a mocked transport."""
    client = HttpChatClient(
        base_url=base_url,
        api_key=api_key,
        model=model,
        max_tokens=64,
        temperature=0.0,
        timeout_s=5.0,
    )
    client._client = httpx.AsyncClient(
        timeout=5.0, transport=httpx.MockTransport(handler)
    )
    return client


# ---------------------------------------------------------------------------
# HttpEmbeddingClient — happy path
# ---------------------------------------------------------------------------


def test_embedding_url_uses_base_url_and_path() -> None:
    """URL must be ``{base}/embeddings`` — no string-concat artefacts."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return _json_response(200, {"data": [{"embedding": [0.1, 0.2, 0.3]}]})

    client = _make_embedding_client(handler)
    try:
        _run(client.embed(["hello"]))
    finally:
        _run(client.close())

    assert captured["url"] == "https://api.openai.com/v1/embeddings"


def test_embedding_url_handles_trailing_slash() -> None:
    """A trailing slash on ``base_url`` must not produce a double slash."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return _json_response(200, {"data": [{"embedding": [0.1, 0.2, 0.3]}]})

    client = _make_embedding_client(handler, base_url="https://api.openai.com/v1/")
    try:
        _run(client.embed(["hello"]))
    finally:
        _run(client.close())

    # Exactly one slash between host and path — no ``//embeddings``.
    assert captured["url"] == "https://api.openai.com/v1/embeddings"


def test_embedding_sends_bearer_authorization() -> None:
    """``Authorization: Bearer <KEY>`` must be present with the configured key."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return _json_response(200, {"data": [{"embedding": [0.0, 0.0, 0.0]}]})

    client = _make_embedding_client(handler)
    try:
        _run(client.embed(["hello"]))
    finally:
        _run(client.close())

    auth = captured["headers"].get("authorization") or captured["headers"].get(
        "Authorization"
    )
    assert auth == "Bearer sk-test-key-abc123"


def test_embedding_payload_matches_openai_schema() -> None:
    """Body must contain ``input`` (list) and ``model`` (string)."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return _json_response(200, {"data": [{"embedding": [0.0, 0.0, 0.0]}]})

    client = _make_embedding_client(handler)
    try:
        _run(client.embed(["a", "b", "c"]))
    finally:
        _run(client.close())

    body = captured["body"]
    assert body["model"] == "text-embedding-3-small"
    assert body["input"] == ["a", "b", "c"]


def test_embedding_parses_200_response() -> None:
    """A 200 response is parsed into a list of vectors in input order."""
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(
            200,
            {
                "data": [
                    {"embedding": [0.1, 0.2, 0.3]},
                    {"embedding": [0.4, 0.5, 0.6]},
                ]
            },
        )

    client = _make_embedding_client(handler)
    try:
        vectors = _run(client.embed(["x", "y"]))
    finally:
        _run(client.close())

    assert vectors == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]


# ---------------------------------------------------------------------------
# HttpEmbeddingClient — failure paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [401, 429, 500, 502, 503])
def test_embedding_raises_typed_error_on_4xx_5xx(status: int) -> None:
    """Non-2xx must raise ``EmbeddingError`` — never a generic crash."""
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(status, {"error": "boom"})

    client = _make_embedding_client(handler)
    try:
        with pytest.raises(EmbeddingError) as exc:
            _run(client.embed(["hello"]))
        # Error message surfaces the upstream status so operators can
        # triage without leaking the API key.
        assert str(status) in str(exc.value)
    finally:
        _run(client.close())


def test_embedding_raises_typed_error_on_dim_mismatch() -> None:
    """Response vector length differs from configured ``dim`` must raise."""
    def handler(request: httpx.Request) -> httpx.Response:
        # Configured dim=3, but upstream returns 5 floats.
        return _json_response(
            200, {"data": [{"embedding": [0.0, 0.0, 0.0, 0.0, 0.0]}]}
        )

    client = _make_embedding_client(handler, dim=3)
    try:
        with pytest.raises(EmbeddingError) as exc:
            _run(client.embed(["hello"]))
        msg = str(exc.value).lower()
        # Surfaces the dimension mismatch, not just a generic "bad payload".
        assert "dim" in msg or "dimension" in msg
    finally:
        _run(client.close())


def test_embedding_raises_typed_error_on_network_failure() -> None:
    """``httpx.HTTPError`` from the transport must surface as ``EmbeddingError``."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated DNS failure")

    client = _make_embedding_client(handler)
    try:
        with pytest.raises(EmbeddingError):
            _run(client.embed(["hello"]))
    finally:
        _run(client.close())


# ---------------------------------------------------------------------------
# HttpChatClient — happy path
# ---------------------------------------------------------------------------


def test_chat_url_uses_chat_completions_path() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return _json_response(
            200,
            {"choices": [{"message": {"content": "grounded answer"}}]},
        )

    client = _make_chat_client(handler)
    try:
        _run(client.complete("What is X?", [_cite()]))
    finally:
        _run(client.close())

    assert captured["url"] == "https://api.openai.com/v1/chat/completions"


def test_chat_sends_bearer_authorization() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return _json_response(
            200,
            {"choices": [{"message": {"content": "grounded answer"}}]},
        )

    client = _make_chat_client(handler)
    try:
        _run(client.complete("What is X?", [_cite()]))
    finally:
        _run(client.close())

    auth = captured["headers"].get("authorization") or captured["headers"].get(
        "Authorization"
    )
    assert auth == "Bearer sk-test-key-abc123"


def test_chat_payload_includes_messages_model_and_params() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return _json_response(
            200,
            {"choices": [{"message": {"content": "ok"}}]},
        )

    client = _make_chat_client(handler)
    try:
        _run(client.complete("What is X?", [_cite()]))
    finally:
        _run(client.close())

    body = captured["body"]
    assert body["model"] == "gpt-4o-mini"
    assert body["max_tokens"] == 64
    assert body["temperature"] == pytest.approx(0.0)
    messages = body["messages"]
    assert isinstance(messages, list) and len(messages) >= 1
    # System prompt must always be the first message.
    assert messages[0]["role"] == "system"


def test_chat_parses_200_response_into_string() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(
            200,
            {"choices": [{"message": {"content": "short, grounded reply"}}]},
        )

    client = _make_chat_client(handler)
    try:
        out = _run(client.complete("Q", [_cite()]))
    finally:
        _run(client.close())

    assert out == "short, grounded reply"


# ---------------------------------------------------------------------------
# HttpChatClient — failure paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [401, 429, 500, 502, 503])
def test_chat_raises_typed_error_on_4xx_5xx(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(status, {"error": "boom"})

    client = _make_chat_client(handler)
    try:
        with pytest.raises(ChatError) as exc:
            _run(client.complete("Q", [_cite()]))
        assert str(status) in str(exc.value)
    finally:
        _run(client.close())


def test_chat_raises_typed_error_on_malformed_body() -> None:
    """Response missing ``choices`` must surface as ``ChatError``."""
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(200, {"unexpected": "shape"})

    client = _make_chat_client(handler)
    try:
        with pytest.raises(ChatError):
            _run(client.complete("Q", [_cite()]))
    finally:
        _run(client.close())


def test_chat_raises_typed_error_on_network_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated DNS failure")

    client = _make_chat_client(handler)
    try:
        with pytest.raises(ChatError):
            _run(client.complete("Q", [_cite()]))
    finally:
        _run(client.close())