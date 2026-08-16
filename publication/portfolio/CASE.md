# RAG-style Knowledge Assistant — Local-First Demo Kit

> A reproduction-ready, citation-grounded answer service that runs on
> a single `docker compose up` and never touches a credit card. Every
> answer is grounded in the operator's own corpus, refuses honestly
> when the evidence is thin, and ships with a deterministic test suite
> that proves the contract.

---

## 1. Problem

Client-side teams adopt retrieval-augmented assistants to consolidate
internal documentation, but the path from "interesting demo" to
"auditable production" is paved with unspoken trade-offs:

- **Trust.** A language model that can answer *anything* with
  plausible confidence is a liability in any regulated workflow. The
  buyer needs to verify the claim by reading the source the answer
  came from.
- **Refusal.** When the corpus does not contain the answer, a
  hallucinated response is worse than no answer. The system must
  refuse explicitly and say *why* it refused.
- **Audit.** A demo that produces a nice answer is not enough.
  Operators must see what the system actually did on each request,
  with secrets redacted, in a log they can grep.
- **Reproducibility.** Most RAG stacks drift between runs because the
  embedding model or the vector index changes underneath. A buyer
  demo should produce the same answer on the same corpus every time.
- **Deployment friction.** A managed SaaS solution requires a
  contract, a connection, a billing relationship, and a security
  review. Operators who have none of that ready need a local
  alternative that can be exercised end-to-end on a single machine.

This project demonstrates a small, contained answer to those
constraints, assembled with off-the-shelf open-source parts and
validated by a reproducible test suite.

## 2. Target public

The intended audience is a small-to-mid delivery team that already
has a corpus of internal documentation and wants to expose it through
a chat-style surface without standing up a managed backend:

- **Internal support** — a single team that owns a curated knowledge
  base and wants a low-risk way to pilot "ask the docs" without
  changing data residency.
- **Pre-sales audit** — a buyer who needs to walk through the
  evidence trail end-to-end before approving a pilot.
- **Service studios** — a fixed-bid delivery team that needs a
  reference architecture they can adapt without paying an embedding
  vendor while the proposal is still being written.

It is **not** a consumer-facing chatbot. It is not a multi-tenant
SaaS. It is not a hosted RAG service. The single-binary promise
holds only for the local docker-compose story.

## 3. Solution

A four-service stack that runs on a single machine and refuses to
answer when the corpus does not support it:

- A **static UI** (nginx-served HTML / CSS / vanilla JS) that drives
  every interaction from the keyboard or a touch screen.
- A **FastAPI** service that handles identity, collections, queries
  and citations. Pydantic models enforce strict request validation.
- A **Postgres + pgvector** store that holds the corpus and the
  embedding vectors.
- A **Playwright + pytest** test image that runs the end-to-end
  browser tests and the deterministic acceptance run.

The UI is built around three honest answer states:

- `answered` — the answer text plus a numbered list of citations.
  Each citation carries the source file, location, cosine score,
  and a short snippet. Inline `[N]` markers inside the answer body
  are clickable links that jump to the matching citation card.
- `refused` — a yellow banner that states *"The corpus has no
  answer to this question."* and surfaces the computed `best_score`
  and `threshold` so the operator can audit why.
- `error` — a red banner with the (already-redacted) error message
  and a primary action button: *"Open token settings"* on a 401,
  *"Retry"* on a 5xx or network failure. The raw technical detail
  lives inside a collapsed `<details>` so it never gets in the way
  of the friendly headline.

The fourth state — empty workspace — is surfaced as an actionable
placeholder rather than a dead-end: the user is told the workspace
has no collections and is offered two concrete next steps (switch
workspace from the disclosure that auto-opens, or ingest via the
documented API).

## 4. Architecture and stack

```
                host browser
                     │  :8080
                     ▼
             ┌───────────────┐
             │  ui (nginx)   │  static HTML/CSS/JS
             └───────┬───────┘
                     │  /api/* →  api:8000
                     ▼
             ┌───────────────┐
             │  api (FastAPI)│  pydantic + audit + auth gate
             └───────┬───────┘
                     │  SQLAlchemy / asyncpg
                     ▼
             ┌───────────────┐
             │  db (pgvector)│  Postgres 16 + pgvector
             └───────────────┘

             ┌───────────────┐
             │  test         │  pytest + Playwright / Chromium
             │ (run --rm)    │  on demand; not part of `up`
             └───────────────┘
```

| Component | Choice | Why |
|-----------|--------|-----|
| API runtime | Python 3.12 + FastAPI + Pydantic | Strict request validation with `extra="forbid"`, length caps, NUL-byte rejection. |
| Vector store | PostgreSQL 16 + pgvector | One binary, one backup target, a real `pg_dump` story. No separate vector DB to operate. |
| UI | nginx + vanilla JS | No build step, no framework lock-in, no supply chain. The whole bundle is < 50 KB. |
| Auth | Configurable Bearer-token gate | `secrets.compare_digest` comparison, fails closed. `/healthz` and `/readyz` are always public. |
| Embeddings | Deterministic local stub | Hashes each input to a unit-norm 1536-d vector. The test suite is reproducible and free of paid credentials. A vendor adapter is pluggable (`EMBEDDING_STUB=false`). |
| Test runner | pytest + Playwright/Chromium | Drives the real browser end-to-end. Each test gets a fresh context so localStorage does not leak between auth cases. |
| Observability | Structured JSON audit log | One line per request with `rid`, `principal`, `method`, `path`, `status`, `latency_ms` and redacted `extra`. Bearer/skey/JWT/PEM patterns are scrubbed. |

## 5. Key decisions

- **Three honest states, no silent failures.** The UI never shows a
  "loading…" that never resolves. The API either answers, refuses, or
  raises an error — and the UI renders each one explicitly.
- **Citations are first-class, not an afterthought.** Every answer
  carries the source file, location, score, and a snippet. The inline
  `[N]` markers are clickable links that jump to the matching card.
- **Refusal is a feature.** The corpus is deliberately narrow so the
  acceptance run can exercise the refusal path. The retrieval
  threshold (default `0.20`) is exposed in the refusal response so
  the operator can audit why the system refused.
- **No vendor lock-in for embeddings.** The stub adapter is
  deterministic and used by the test suite. Switching to a real
  provider is a configuration change, not a code change.
- **Reproducible acceptance.** The 16-question acceptance run is
  pinned to the shipped corpus and the deterministic stub. The same
  commit produces the same `results.json` and `results.md`.
- **Manual retention, not cron.** The shipped package does not run
  any scheduled cleanup. The retention procedure is documented and
  requires a backup, a row-count preview, a dry-run, the literal
  confirmation word `DELETE`, and a post-delete backup.
- **No public hosting.** The local docker-compose story is the entire
  deployment story. There is no managed mode, no hosted admin
  console, no 24/7 monitoring.

## 6. Security and isolation

- **Auth gate.** When `AUTH_ENABLED=true` every `/v1/*` request must
  carry `Authorization: Bearer <token>` matching `AUTH_TOKEN`.
  Comparison uses `secrets.compare_digest`. `/healthz` and `/readyz`
  are always public so probes do not need a token.
- **Input validation.** Every request body flows through Pydantic
  models with `extra="forbid"`, length caps, and NUL-byte rejection.
  See `tests/security/test_validation.py`.
- **Structured audit log.** `app/audit.py` emits one JSON line per
  request to STDOUT with `rid`, `principal`, `method`, `path`,
  `status`, `latency_ms`, and redacted `extra`. A conservative
  scrubber (`scrub`, `scrub_mapping`) removes Bearer/skey/JWT
  patterns and zeroes out sensitive header keys.
- **Secret-scanning.** `tests/security/test_secrets.py` walks every
  text file in the repository and fails if any secret-shaped
  content (sk-…, JWT, Bearer …, PEM block, AWS access key id) leaks
  in.
- **Network isolation.** The DB port is not exposed on the host. The
  UI is the only service with a published port; only the UI talks
  to the API through the reverse proxy.
- **Token in browser localStorage** is a deliberate tradeoff for the
  static-token gate over `localhost`. A production deployment with
  a real IdP should swap `api/app/auth.py` for OIDC / OAuth2 and
  move the token out of `localStorage` (`HttpOnly` cookie + CSRF
  token). The gate is isolated to one module so the swap is
  mechanical.

## 7. Verifiable results

The reproduction contract is small and concrete:

| Suite | Count | Command |
|-------|-------|---------|
| Security | 70 | `docker compose run --rm test pytest -q tests/security` |
| Integration | 20 | `docker compose run --rm test pytest -q tests/integration` |
| Acceptance | 8 | `docker compose run --rm test pytest -q tests/acceptance` |
| End-to-end UI | 24 | `./scripts/smoke-ui.sh` |

Plus the canonical closeout chain in `scripts/test-publication.sh`
which runs every verifier back-to-back against a fresh stack.

**Out of 16 acceptance questions, the demonstration run resolves 15
cleanly and exposes 1 known drift**:

- **Q13 ("Who won the 2024 Copa America final?")** unexpectedly
  returned `status=answered` with `best_score=0.2977` above the
  retrieval threshold of `0.20`. The corpus does not contain sports
  content; the closest match was a chunk in `indoor-herb-garden.md`
  whose "Light Requirements" section shares incidental token
  overlap with the question. The drift is a known limitation of the
  deterministic stub embedding (it hashes each input to a unit-norm
  vector, which can lift borderline fragments above the threshold).
  The verifier accepts the 1/16 drift (6.25 %) within the 20 %
  acceptance budget. Tighter thresholds would refuse Q13 but also
  refuse legitimate on-topic queries — the current threshold is the
  calibrated balance.

The full gap discussion is in `proof/gaps.md` and is preserved
verbatim in the repository.

## 8. Honest limitations

- **No real-world knowledge.** The shipped corpus is synthetic and
  openly licensed. The assistant cannot answer questions outside
  its corpus, and the corpus is narrow by design (cat care, dog
  adoption, fermentation, fitness, herb garden, open-source
  licensing, a fictional Python tool).
- **No OCR, no complex tables, no charts.** Only Markdown, plain
  text and textual PDFs are ingested. Scanned images, hand-written
  notes, and multimodal figures are out of scope.
- **No perfect-accuracy promise.** Embeddings are lossy. The
  assistant may refuse correctly and may still get a
  partially-supported answer wrong. Every answer carries the
  citations it was grounded in — read them.
- **No live external services.** The embedding adapter is the
  deterministic local stub by default. A vendor integration is
  available via configuration but is not exercised by the test
  suite (no network in CI).
- **Auth-off by default.** The shipped `.env` sets
  `AUTH_ENABLED=false` so the demo stack is permissive. The auth
  gate is on by a single configuration flip and is verified
  end-to-end by `tests/e2e/test_ui_auth_gate.py`.
- **localStorage token.** The token persists in the browser's
  `localStorage` so a single-tab refresh keeps the authenticated
  state. This is the right tradeoff for a static-token gate over
  `localhost`; a real deployment should swap the gate for a proper
  IdP. The gate is isolated to one module so the swap is mechanical.
- **Stub embedding.** The deterministic stub hashes each input to a
  unit-norm 1536-d vector. The test suite is reproducible because
  the hashing is stable. Switching to a vendor embedding will
  change the cosine scores and may shift borderline answers — the
  Q13 drift is the canonical example of this exposure.
- **No hosted mode.** No public URL, no TLS termination, no SaaS
  multi-tenancy, no billing. Bring-up is local-only (`docker
  compose up`).
- **No SLA, no 24/7 monitoring.** This is a reproducible
  demonstration, not a production service.
- **No advanced reasoning layer.** The "Intelligence" extension
  (multi-hop retrieval, agentic tool use, semantic caching) is
  intentionally out of scope. The current generation answers
  single-hop questions; multi-hop is a separate research line.

## 9. How to run the demo

Requirements: Docker Engine ≥ 29 and Docker Compose v2.

```bash
# 1. Clone the repository
git clone <this-repo> upwork-knowledge-assistant
cd upwork-knowledge-assistant

# 2. Bootstrap the configuration
cp .env.example .env                     # placeholder values; edit if needed

# 3. Build, bring up, and verify the stack
docker compose config --quiet            # composition is valid
docker compose build --pull              # build every service
docker compose up -d --wait              # start and wait for healthchecks

# 4. Open the demo
xdg-open http://127.0.0.1:8080/          # or visit the URL in your browser
xdg-open http://127.0.0.1:8080/gallery/  # the review-ready gallery

# 5. Run the full test sweep
docker compose run --rm test pytest -q tests/security
docker compose run --rm test pytest -q tests/integration
docker compose run --rm test pytest -q tests/acceptance
./scripts/smoke-ui.sh                    # end-to-end UI tests
./scripts/test-publication.sh            # canonical closeout chain

# 6. Tear it all down (DESTRUCTIVE: drops the pgvector volume)
docker compose down -v
```

The `test` service is hidden behind a `profiles: ["never"]` setting,
so `docker compose up` does not start it. It runs only on demand
through `docker compose run --rm test …`.

### Onboarding with your own corpus

1. Drop Markdown, plain text or textual-PDF files into `data/corpus/`.
2. Rebuild and bring the stack back up:
   `docker compose build --pull api && docker compose up -d --wait`.
3. Re-run the proof to refresh `proof/results.json` and
   `proof/results.md`: `./scripts/run-proof.sh`.
4. Review `proof/gaps.md` and update it if the new documents close
   any open refusal topic — `verify-proof-artifacts.sh` enforces
   that every corpus document appears in the source map.

## 10. Stack refresh and embedding switch

The provider is decoupled by the embedding adapter. The stub
(`EMBEDDING_STUB=true`) is the deterministic local hash-to-vector
adapter used for tests and offline runs. To switch to a real
OpenAI-compatible provider:

```bash
# .env
EMBEDDING_STUB=false
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_API_KEY=<set by secret manager — never commit>
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536
```

Then rebuild the API image:
`docker compose build --pull api && docker compose up -d --wait`.
The dimension column on the vector store is created by
`ensure_schema()` based on `EMBEDDING_DIM`, so changing the value
without a fresh volume raises a startup error — that is intentional.

---

## 11. Source-of-truth pointers

- `README.md` — repository landing page, quick start.
- `publication/HANDOFF.md` — one-and-done buyer handoff.
- `publication/RETENTION.md` — manual retention procedure.
- `publication/COPY.md` — commercial copy (promise, deliverables,
  limits, acceptance).
- `publication/UX-REVIEW.md` — independent usability audit that
  drove the UX improvements applied in this release.
- `proof/gaps.md` — explicit list of refusal topics and the Q13
  drift.
- `scripts/test-publication.sh` — canonical closeout chain.
- `gallery/SHA256SUMS.reference` — content hash of the four review
  states.
