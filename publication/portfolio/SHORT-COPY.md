# Short Copy — Reusable Paragraphs

> Three self-contained blocks you can paste into a proposal, a
> résumé bullet, a portfolio website, or a sales conversation.
> Each block stands on its own; concatenate them as needed.

---

## 1. The one-paragraph summary

A local-first, citation-grounded answer service that runs on a
single `docker compose up` and refuses to answer when the corpus
does not support it. The stack is four containers: a static
nginx-served UI, a FastAPI service with strict Pydantic request
validation, a Postgres + pgvector store, and a Playwright + pytest
test image that drives the end-to-end browser tests. The UI
surfaces three honest answer states — `answered` with clickable
inline citations, `refused` with the computed score and threshold,
and `error` with a friendly banner and a primary action button.
The suite is reproducible: 70 security + 20 integration + 8
acceptance + 24 end-to-end UI tests, all green on a fresh clone.

---

## 2. The three-sentence elevator pitch

A small, contained retrieval-augmented assistant that turns a
local folder of Markdown, plain text and textual PDF documents into
a chat-style surface with citations, refusals, and a structured
audit log. It runs on a single machine, does not require a credit
card or a hosted backend, and ships with a deterministic test
suite that proves the contract. The current release adopts five
independent UX improvements identified by an external audit —
clickable citations, human error messages, actionable empty
states, mobile-friendly touch targets, and visible keyboard focus
— and bundles them with a sanitized portfolio case study that
public visitors can read alongside the code.

---

## 3. The trust-and-trade-off block

The four honest trade-offs that make the system auditable: the
retrieval threshold is exposed in every refusal so the operator
can see why the system refused, every request flows through a
structured JSON audit logger with redaction of secret-shaped
payloads, the bearer token is compared with `secrets.compare_digest`
and fails closed, and the test suite runs the same commands on
every clone — there is no hidden state between the suite and the
verifiable numbers. The system is intentionally narrow: no OCR,
no complex tables, no live external services by default, no
hosted mode, no 24/7 monitoring, no managed SLA. Switching to a
real embedding provider is a configuration change, not a code
change.

---

## 4. The specific-results block

End-to-end test results from a fresh clone: 70 security tests, 20
integration tests, 8 acceptance tests, and 24 end-to-end UI tests
(ten of which are dedicated to the UX improvements adopted in
this release). The 16-question acceptance run resolves 15 cleanly
and exposes 1 known stub-embedding drift (Q13, "Who won the 2024
Copa America final?", answered with `best_score=0.2977` above the
`0.20` threshold because the closest match shares incidental
token overlap with the question). The drift is documented in
the repository gap report and is within the 20 % acceptance
budget.

---

## 5. The "who is this for" paragraph

The intended audience is a small-to-mid delivery team that
already has a curated knowledge base and wants to expose it
through a chat-style surface without standing up a managed
backend. It is not a consumer-facing chatbot, not a multi-tenant
SaaS, and not a hosted RAG service. The single-binary promise
holds only for the local docker-compose story; a production
deployment swaps the static-token gate for a real IdP and moves
the token out of `localStorage`. The gate is isolated to one
module so the swap is mechanical.
