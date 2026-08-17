"""OpenAI-compatible chat client — REQ-004 grounded answer generation.

The chat client is the LLM gateway that turns a set of relevance-filtered
chunks into a short, citation-backed answer. The contract is the same
whether the implementation is the dependency-free ``StubChatClient``
used by tests or the ``HttpChatClient`` that talks to a live
OpenAI-compatible endpoint:

    1. The model receives ONLY the retrieved passages as context.
    2. The model is forbidden from inventing facts.
    3. The model returns ``INSUFFICIENT_EVIDENCE`` when the context
       does not answer the question. This token is the only signal the
       HTTP caller interprets as a soft refusal — the hard refusal is
       gated by the per-citation relevance filter upstream.

The factory ``make_chat_client`` selects stub vs live by reading
``CHAT_STUB`` from settings (default: ``True`` so a fresh clone has
working tests without an API key).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.retrieve import Citation

log = logging.getLogger("upworkkb.chat")


class ChatError(RuntimeError):
    """Raised by chat providers on transient/permanent failures."""


class ChatClient(Protocol):
    async def complete(self, question: str, citations: list[Citation]) -> str: ...
    async def close(self) -> None: ...


# Token the chat model emits to signal the context did not contain an
# answer. Exposed as a module constant so callers and tests share a
# single source of truth.
REFUSAL_TOKEN = "INSUFFICIENT_EVIDENCE"

_SYSTEM_PROMPT = (
    "You are a careful, grounded assistant. You answer questions ONLY "
    "using the numbered context passages provided. You never invent "
    "facts. If the context does not contain enough information to "
    "answer the question, you reply with exactly the literal text "
    f"{REFUSAL_TOKEN}. You keep answers short (1-3 sentences), in the "
    "same language as the question, and you cite passages by their "
    "number (e.g. [1])."
)


def _build_messages(question: str, citations: list[Citation]) -> list[dict]:
    """Render the user-facing prompt with numbered context passages."""
    ctx_lines = []
    for i, c in enumerate(citations, start=1):
        loc_parts: list[str] = []
        if c.section:
            loc_parts.append(c.section)
        if c.page is not None:
            loc_parts.append(f"page {c.page}")
        loc = f" ({', '.join(loc_parts)})" if loc_parts else ""
        ctx_lines.append(f"[{i}] {c.file_name}{loc}:\n{c.text}")
    context = "\n\n".join(ctx_lines)
    user = (
        f"Context passages (numbered):\n\n{context}\n\n"
        f"Question: {question.strip()}\n\n"
        "Answer in 1-3 short sentences using ONLY the passages above. "
        "Cite passages by number like [1]. If the context does not "
        f"support an answer, reply exactly {REFUSAL_TOKEN}."
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


@dataclass
class StubChatClient:
    """Deterministic, dependency-free chat stub for tests.

    The stub never fabricates content: it surfaces the leading sentence
    of the top-ranked citation verbatim plus a citation pointer. This
    mirrors a real model's contract (no invention) while remaining
    reproducible across runs and machine-readable for downstream
    assertions.

    The stub returns ``INSUFFICIENT_EVIDENCE`` only when there are no
    citations to summarise. The relevance gate (per-citation
    filter) upstream is what guarantees that scenario is rare.
    """

    async def complete(self, question: str, citations: list[Citation]) -> str:
        if not citations:
            return REFUSAL_TOKEN
        top = citations[0]
        first_line = top.text.strip().split("\n", 1)[0].strip()
        snippet = first_line[:280].rstrip()
        if snippet and not snippet.endswith((".", "!", "?")):
            snippet = snippet.rstrip(".") + "."
        return f"{snippet} See [1] for the source."

    async def close(self) -> None:
        return None


@dataclass
class HttpChatClient:
    """Live OpenAI-compatible chat client.

    Sends ``POST {base_url}/chat/completions`` with a system
    instruction plus a user message that quotes the retrieved passages
    verbatim. The model is asked (via the system prompt) to emit
    ``INSUFFICIENT_EVIDENCE`` when the context is empty; the per-citation
    relevance filter upstream is the hard refusal gate.
    """

    base_url: str
    api_key: str
    model: str
    max_tokens: int = 400
    temperature: float = 0.2
    timeout_s: float = 30.0
    _client: httpx.AsyncClient | None = None

    def __post_init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=self.timeout_s)

    async def complete(self, question: str, citations: list[Citation]) -> str:
        if not citations:
            return REFUSAL_TOKEN
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_s)
        messages = _build_messages(question, citations)
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        try:
            response = await self._client.post(url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise ChatError(f"chat request failed: {exc}") from exc
        if response.status_code >= 400:
            raise ChatError(
                f"chat provider returned {response.status_code}: "
                f"{response.text[:300]}"
            )
        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ChatError(
                f"chat provider returned malformed body: {payload!r}"
            ) from exc
        text = (content or "").strip()
        return text or REFUSAL_TOKEN

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def make_chat_client(
    *,
    stub: bool,
    base_url: str,
    api_key: str,
    model: str,
    max_tokens: int = 400,
    temperature: float = 0.2,
    timeout_s: float = 30.0,
) -> ChatClient:
    """Factory selected on env (``CHAT_STUB``)."""
    if stub:
        return StubChatClient()
    return HttpChatClient(
        base_url=base_url,
        api_key=api_key,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout_s=timeout_s,
    )


__all__ = [
    "ChatClient",
    "StubChatClient",
    "HttpChatClient",
    "ChatError",
    "REFUSAL_TOKEN",
    "make_chat_client",
]
