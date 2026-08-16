"""OpenAI-compatible embedding adapter (DEC-005).

The real network call lives behind a Protocol. For TASK-001 we ship a
deterministic stub that produces a stable dim-sized vector keyed on the
SHA-256 of the input text. This makes the test suite reproducible without an
API key and without coupling the product to a specific vendor.

Switch to the live client by setting `EMBEDDING_STUB=false` in the environment.

TASK-002: the stub became *token-aware* so that two topically similar inputs
land near each other in cosine space. Without this refinement, the raw
hash-folded stub produces quasi-random vectors, which makes retrieval
indistinguishable from random top-k. The token-aware layer is a hashing
trick (à la classical IR): each token is hashed to a dimension ridge, so
shared tokens contribute to shared components. A small document fingerprint
is added on top so distinct texts with identical tokens still drift apart.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Protocol


class EmbeddingError(RuntimeError):
    """Raised by embedding providers on transient/permanent failures."""


class EmbeddingClient(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    async def close(self) -> None: ...


@dataclass
class StubEmbeddingClient:
    """Deterministic local client — same input → same vector, every time.

    Two topically related inputs land near each other in cosine space
    (token-aware layer). Same input → identical vector (document fingerprint).
    """

    dim: int = 1536
    model: str = "stub-local-deterministic-v2"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [_deterministic_vector(t, self.dim) for t in texts]

    async def close(self) -> None:
        return None


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


def _deterministic_vector(text: str, dim: int) -> list[float]:
    """Hash-fold the text into a unit-norm `dim`-dimensional vector.

    Two layers:
      1. Token-level hashing trick: each token is hashed to a ridge of
         nearby dimensions. Shared tokens → shared components → similar
         vectors (cosine). This is what makes retrieval non-random.
      2. Document fingerprint: a small SHA-256 derived offset so two
         distinct documents with the same token bag still drift apart.
    """
    vec = [0.0] * dim

    # Layer 1 — token-level contribution. Each token picks a sign from
    # its own SHA digest so the same token always has the same sign but
    # unrelated tokens do not cancel each other out spuriously. This
    # keeps the cosine between a query and a same-topic chunk higher
    # than between two random texts.
    for tok in _tokenize(text):
        h = hashlib.sha256(tok.encode("utf-8")).digest()
        idx = int.from_bytes(h[:4], "big") % dim
        sign = 1.0 if (h[4] & 1) else -1.0
        # Ridge of 7 consecutive dimensions (idx ± 3) to spread the
        # contribution and keep the vector dense.
        for offset in range(-3, 4):
            vec[(idx + offset) % dim] += sign

    # Layer 2 — document fingerprint (small perturbation).
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    pool = bytearray()
    counter = 0
    while len(pool) < dim * 4:
        counter += 1
        pool.extend(hashlib.sha256(digest + counter.to_bytes(4, "big")).digest())
    for i in range(dim):
        b = int.from_bytes(bytes(pool[i * 4 : i * 4 + 4]), "big") / 2**32
        vec[i] += (b - 0.5) * 0.05  # tiny noise, deterministic

    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def make_client(*, stub: bool, dim: int) -> EmbeddingClient:
    """Factory selected on env (`EMBEDDING_STUB`).

    Real network client is intentionally NOT shipped in TASK-001; only the
    interface and a usable stub.
    """
    if stub:
        return StubEmbeddingClient(dim=dim)
    raise EmbeddingError(
        "live embedding client is not wired in TASK-001; set EMBEDDING_STUB=true"
    )


__all__ = [
    "EmbeddingClient",
    "StubEmbeddingClient",
    "EmbeddingError",
    "make_client",
]
