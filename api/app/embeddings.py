"""OpenAI-compatible embedding adapter (DEC-005).

Two clients share a ``Protocol``:

  - ``StubEmbeddingClient`` — deterministic, dependency-free hash fold.
    Used by tests and CI so the suite has no network requirement.
  - ``HttpEmbeddingClient`` — thin httpx wrapper around any
    OpenAI-compatible ``POST /v1/embeddings`` endpoint. Selected when
    ``EMBEDDING_STUB=false``.

The selected switch is ``EMBEDDING_STUB``. Default ``true`` keeps a
fresh clone fully offline; flipping it to ``false`` in production
wires the live adapter. Both clients normalise their output so the
downstream pipeline only sees ``list[list[float]]`` of ``dim``
dimensions.

Stub design notes
-----------------

The stub is a token-bag hash fold:

  1. Tokenise + drop stopwords + drop sub-3-char tokens.
  2. Naive stem (``s/es/ing/ies`` suffix) so ``cat`` and ``cats``
     land in the same neighbourhood.
  3. Hash each stemmed token to a 7-dim ridge (idx ± 3) in a fixed
     ``dim``-sized space; sign is fixed per token.
  4. L2-normalise the result.

The previous build layered a SHA-256 derived document fingerprint on
top, which produced spuriously high cosine between unrelated texts
(e.g. ``What is the capital of Mongolia?`` scoring 0.49 against the
cat-care corpus). That fingerprint is gone; the per-citation
relevance filter now relies on the cleaner token-only signal.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Protocol

import httpx


class EmbeddingError(RuntimeError):
    """Raised by embedding providers on transient/permanent failures."""


class EmbeddingClient(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    async def close(self) -> None: ...


@dataclass
class StubEmbeddingClient:
    """Deterministic local client — same input → same vector, every time.

    Two topically related inputs land near each other in cosine space
    (token-aware layer). Same input → identical vector.
    """

    dim: int = 1536
    model: str = "stub-local-deterministic-v3"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [_deterministic_vector(t, self.dim) for t in texts]

    async def close(self) -> None:
        return None


@dataclass
class HttpEmbeddingClient:
    """Live OpenAI-compatible embedding client.

    Sends ``POST {base_url}/embeddings`` with the configured model and
    bearer token. Errors are surfaced as ``EmbeddingError`` so the
    caller can map them to a 502 / 503 without leaking the upstream
    status.
    """

    base_url: str
    api_key: str
    model: str
    dim: int = 1536
    timeout_s: float = 30.0
    _client: httpx.AsyncClient | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=self.timeout_s)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_s)
        url = f"{self.base_url.rstrip('/')}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {"input": texts, "model": self.model}
        try:
            response = await self._client.post(url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"embedding request failed: {exc}") from exc
        if response.status_code >= 400:
            raise EmbeddingError(
                f"embedding provider returned {response.status_code}: "
                f"{response.text[:300]}"
            )
        try:
            payload = response.json()
            data = payload["data"]
            vectors = [item["embedding"] for item in data]
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbeddingError(
                f"embedding provider returned malformed body: {payload!r}"
            ) from exc
        # Dimension guard — upstream embeddings must match the
        # configured ``dim`` so the pgvector column type stays
        # consistent across providers. A mismatch is a configuration
        # error, not a transient failure.
        for idx, vec in enumerate(vectors):
            if len(vec) != self.dim:
                raise EmbeddingError(
                    f"embedding vector dim mismatch at index {idx}: "
                    f"expected {self.dim}, got {len(vec)}"
                )
        return vectors

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# Conservative stopword set — kept tiny so we never accidentally strip a
# domain term. The list is intentionally hard-coded so the embedding is
# reproducible across processes.
_STOPWORDS = frozenset(
    {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "and", "or", "of", "to", "in", "on", "at", "for", "with", "by",
        "as", "it", "this", "that", "from", "if", "but", "not", "no",
        "do", "does", "did", "will", "would", "can", "could", "should",
        "may", "might", "must", "shall", "have", "has", "had",
        "i", "you", "he", "she", "we", "they", "them", "their", "its",
        "my", "your", "our", "their", "his", "her",
        "what", "which", "who", "when", "where", "why", "how",
        "also", "than", "then", "so", "such", "these", "those",
        "there", "here", "any", "all", "some", "more", "most",
        "one", "two", "three", "four", "five",
    }
)

# Tighter token regex: alphanumerics + a small set of accents. Keeps names
# like "São" or "naïve" available while ignoring punctuation.
_TOKEN_RE = re.compile(r"[a-zà-ÿ0-9]+", re.IGNORECASE)


def _tokenize(text: str) -> list[str]:
    raw = _TOKEN_RE.findall(text.lower())
    return [t for t in raw if t not in _STOPWORDS and len(t) > 2]


def _stem(token: str) -> str:
    """Crush morphological variants onto a common form.

    Keeps the stub dependency-free — corpus is English, the contractions
    we care about are the usual ``s/es/ing/ies`` suffixes. Without this
    step ``feed`` vs ``feeding`` vs ``feeds`` would not collide in the
    hash-fold and cosine separation between on-topic and unrelated
    texts degrades.
    """
    if len(token) <= 3:
        return token
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("ing") and len(token) > 4:
        return token[:-3]
    if token.endswith("es") and len(token) > 3:
        return token[:-2]
    if token.endswith("s") and len(token) > 3:
        return token[:-1]
    return token


def _deterministic_vector(text: str, dim: int) -> list[float]:
    """Hash-fold the text into a unit-norm ``dim``-dimensional vector.

    Token-level hashing trick: each token is hashed to a ridge of
    nearby dimensions. Shared tokens → shared components → similar
    vectors (cosine). L2-normalised so cosine sits in [-1, 1] in
    principle and [0, 1] in this construction (sign-fixed per token).
    """
    vec = [0.0] * dim
    for tok in (_stem(t) for t in _tokenize(text)):
        h = hashlib.sha256(tok.encode("utf-8")).digest()
        idx = int.from_bytes(h[:4], "big") % dim
        sign = 1.0 if (h[4] & 1) else -1.0
        # Ridge of 7 consecutive dimensions (idx ± 3). The width keeps
        # the vector dense enough that L2 normalisation produces stable
        # cosines while keeping the per-token footprint tight enough
        # that random collisions stay rare in 1536 dims.
        for offset in range(-3, 4):
            vec[(idx + offset) % dim] += sign
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def make_client(
    *,
    stub: bool,
    dim: int,
    base_url: str = "",
    api_key: str = "",
    model: str = "",
    timeout_s: float = 30.0,
) -> EmbeddingClient:
    """Factory selected on ``EMBEDDING_STUB``.

    Tests construct the stub directly with ``StubEmbeddingClient``. The
    factory exists so the live wiring (with credentials from
    environment) lives in one place.
    """
    if stub:
        return StubEmbeddingClient(dim=dim)
    if not base_url or not api_key or not model:
        raise EmbeddingError(
            "live embedding client requires EMBEDDING_BASE_URL, "
            "EMBEDDING_API_KEY, and EMBEDDING_MODEL."
        )
    return HttpEmbeddingClient(
        base_url=base_url,
        api_key=api_key,
        model=model,
        dim=dim,
        timeout_s=timeout_s,
    )


__all__ = [
    "EmbeddingClient",
    "StubEmbeddingClient",
    "HttpEmbeddingClient",
    "EmbeddingError",
    "make_client",
]
