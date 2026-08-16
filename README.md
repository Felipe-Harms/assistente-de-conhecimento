# Upwork Knowledge Assistant

A local, Docker-Compose-first knowledge assistant that grounds answers in a
curated corpus and refuses when the evidence is insufficient. Built as a
proof/production demonstrator on synthetic and openly licensed material.

> **End-to-end UI live.** A static bundle (nginx) consumes a configurable
> brand surface from `GET /v1/identity`, lets the operator pick a collection
> + workspace, submits questions through `POST /v1/query`, and renders one
> of three honest states — *answered* (with citations), *refused*
> (`insufficient_evidence`), or *error*. Auth is configurable via
> `AUTH_ENABLED=true`; when on, the UI shows a bearer-token input and
> forwards `Authorization: Bearer …` on every request. Every request is
> audited in structured JSON via `app.audit`.

---

## Overview

- **Goal.** A reproducible local stack: a FastAPI service, a static UI, and a
  PostgreSQL+pgvector store, plus a `test` image that runs `pytest` (with
  Playwright + Chromium driving the end-to-end UI in `tests/e2e/`).
- **Non-goal.** Not a SaaS, not a public deployment, not a model fine-tuning
  pipeline. See *Scope & limits* below.
- **Stack.** Python 3.12 (api/test), nginx (ui), PostgreSQL 16 with pgvector
  (db). `docker compose` is the only supported way to bring it up.

## Quick Start

Requirements: Docker Engine ≥ 29 and Docker Compose v2.

```bash
cp .env.example .env                     # placeholder values; edit if needed
docker compose config --quiet            # composition is valid
docker compose build --pull              # build every service
docker compose up -d --wait              # start and wait for healthchecks

curl -fsS http://127.0.0.1:8080/         # confirm UI is reachable
curl -fsS http://127.0.0.1:8080/healthz-ui  # UI internal probe
                                       # `8080` is whatever UI_PORT is set to
docker compose exec api curl -fsS \
   http://127.0.0.1:8000/healthz          # API internal probe

# Run the security smoke tests:
docker compose run --rm test

# Run the E2E UI smoke (REQ-006) — needs the stack up:
./scripts/smoke-ui.sh

# Run the full sweep: security + integration + acceptance + E2E + proof:
./scripts/test-all.sh

# Tear everything down (DESTRUCTIVE: drops the pgvector volume):
docker compose down -v
```

> The `test` service is hidden behind `profiles: ["never"]` so `up` does not
> start it. It runs only on demand.

## Architecture

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
                          │  SQLAlchemy/asyncpg
                          ▼
                  ┌───────────────┐
                  │  db (pgvector)│  Postgres 16 + pgvector extension
                  └───────────────┘

                  ┌───────────────┐
                  │  test         │  pytest + Playwright/Chromium
                  │ (run --rm)    │  on demand; not part of `up`
                  └───────────────┘
```

| Service | Image / build                | Role                                                | Healthcheck |
|---------|------------------------------|-----------------------------------------------------|-------------|
| `db`    | `pgvector/pgvector:pg16`     | Persistent store; runs `db/init.sql` on first boot. | `pg_isready` |
| `api`   | `python:3.12-slim` + FastAPI | `/healthz`, `/readyz`, `/v1/embeddings` (stub).    | `curl /healthz` |
| `ui`    | `nginx:1.29-alpine`          | Static bundle + `/api/*` reverse proxy.             | `wget /healthz-ui` |
| `test`  | `mcr.microsoft.com/playwright/python:v1.49.0-jammy` | pytest + Chromium (prep for REQ-006). | none — `run --rm` only |

Networking: the stack uses two bridge networks — `backend` (api↔db, api↔test)
and `frontend` (host↔ui→api) — so the database is never reachable from the
host directly.

## Configuration

All configuration is sourced from environment variables. `.env.example` is the
canonical, versioned template; the real `.env` is `.gitignore`d and never
ships in the repository.

| Variable                | Purpose                                                     | Default                                 |
|-------------------------|-------------------------------------------------------------|-----------------------------------------|
| `POSTGRES_USER`         | dev DB user                                                 | `upworkkb`                              |
| `POSTGRES_PASSWORD`     | dev DB password                                             | placeholder — replace locally           |
| `POSTGRES_DB`           | dev DB name                                                 | `upworkkb`                              |
| `DATABASE_URL`          | SQLAlchemy-style URL used by the API                        | `postgresql+asyncpg://...@db:5432/...`  |
| `API_LOG_LEVEL`         | uvicorn log level                                           | `INFO`                                  |
| `AUTH_ENABLED`          | toggle the Bearer gate on `/v1/*` (REQ-007)                 | `false`                                 |
| `AUTH_TOKEN`            | pre-shared secret used when `AUTH_ENABLED=true`             | placeholder — set per env               |
| `EMBEDDING_BASE_URL`    | OpenAI-compatible endpoint                                  | `https://api.openai.com/v1`             |
| `EMBEDDING_API_KEY`     | provider key (never commit a real value)                    | placeholder                             |
| `EMBEDDING_MODEL`       | model name passed to the adapter                            | `text-embedding-3-small`                |
| `EMBEDDING_DIM`         | vector dimensionality                                       | `1536`                                  |
| `EMBEDDING_STUB`        | use the deterministic local stub (`true`/`false`)           | `true`                                   |
| `UI_PORT`               | host port for the UI                                        | `8080`                                  |
| `RETENTION_DAYS`        | retention window for audit/chat data (REQ-007)              | `90`                                    |
| `APP_BRAND_NAME`        | brand displayed in the UI header (REQ-006)                  | `Upwork Knowledge Assistant`            |
| `APP_TAGLINE`           | subtitle line under the brand                               | placeholder                             |
| `APP_ACCENT_COLOR`      | CSS color literal used as `--accent` (validated server-side) | `#0284c7`                               |
| `APP_LOGO_URL`          | optional URL of a brand mark (empty disables)               | empty                                   |
| `APP_FOOTER_NOTE`       | free-text footer line                                       | placeholder                             |

### Embedding adapter (DEC-005)

`api/app/embeddings.py` ships a `Protocol` and a deterministic stub client.
The initial release does **not** call any external API; the stub hashes each
input and turns it into a unit-norm 1536-d vector so the test suite stays
reproducible and free of paid credentials. Live vendor calls are out of scope
for this public release.

## Security baseline

- **No secrets in the repo.** Only `.env.example` (placeholder values) is
  versioned; `.env` is in `.gitignore`. The `tests/security/test_secrets.py`
  suite walks every text file in the tree and fails if any secret shape
  (sk-…, JWT, Bearer …, PEM block, AWS access key id) leaks in.
- **Configurable auth gate.** When `AUTH_ENABLED=true` every `/v1/*` request
  must carry `Authorization: Bearer <token>` matching `AUTH_TOKEN`.
  Comparison uses `secrets.compare_digest`. `/healthz` and `/readyz` are
  always public so probes do not need a token.
- **Input validation.** Every request body flows through Pydantic models in
  `app/models.py` with `extra="forbid"`, length caps, and NUL-byte rejection.
  See `tests/security/test_validation.py`.
- **Structured audit log.** `app/audit.py` emits one JSON line per request to
  STDOUT with `rid`, `principal`, `method`, `path`, `status`, `latency_ms`,
  and redacted `extra`. A conservative scrubber (`scrub`, `scrub_mapping`)
  removes Bearer/skey/JWT patterns and zeroes out sensitive header keys. See
  `tests/security/test_audit.py`.
- **Retention.** `RETENTION_DAYS` declares the window for any chat/audit
  records that land in `audit_events` / `chat_messages`. The default is 90
  days. The shipped package does NOT run any retention job; see
  `publication/RETENTION.md` for the documented manual procedure (backup →
  preview → dry-run → DELETE). The column is in place now.
- **Network isolation.** The DB port is **not** exposed on the host. The UI
  is the only service with a published port (8080 by default), and only it
  talks to the API through the reverse proxy.

## Production UI (REQ-006 / REQ-007)

The static bundle at `ui/` is served by nginx and proxies `/api/*` to the
FastAPI service. It is built around three explicit answer states:

- **`answered`** — the answer text plus a numbered list of citations.
  Each citation carries `file_name`, `section` / `page`, the cosine score,
  and a short snippet. Clicking through to `/v1/citations/{chunk_id}` is
  supported but the UI keeps the citation visible inline.
- **`refused`** — a yellow banner that states *“The corpus has no answer
  to this question.”* and surfaces `reason=insufficient_evidence` plus the
  computed `best_score` and `threshold` so the operator can audit why.
- **`error`** — a red banner with the (already-redacted) error message.
  `401` from the API surfaces a *“check your bearer token”* hint.

The brand surface is fully configurable. Set `APP_BRAND_NAME`,
`APP_TAGLINE`, `APP_ACCENT_COLOR`, `APP_LOGO_URL`, `APP_FOOTER_NOTE` in
`.env` and rebuild the API image; the UI fetches the merged payload from
`GET /v1/identity` on every page load. `accent_color` is validated
server-side (`#rgb`, `#rrggbb`, `rgb(…)`, `rgba(…)`); anything else
falls back to `#0284c7`.

Workspace isolation is exposed in the UI via a collapsible switcher
(`<details>`). The active workspace is persisted to `localStorage` and
can also be set via `?workspace=…` on first load.

When `AUTH_ENABLED=true`, the UI:

- Shows a *“Configure token”* button in the topbar and reveals a
  bearer-token input panel.
- Persists the token in `localStorage` (never written to URLs, never
  logged).
- Sends `Authorization: Bearer …` on every `/api/*` request.
- Flips the auth pill between *“Auth required”* / *“Authenticated”*
  / *“Auth disabled”*.

The token never crosses nginx — it is sent from the browser straight
through the proxy to the API, where the `check_bearer()` gate decides.
Production deployments should swap the static-token gate for a real IdP
— the gate is intentionally minimal and isolated to one module so the
replacement is mechanical.

## Scope & limits

This product is intentionally narrow. Anything outside the *in-scope* list is
not built, not promised, and not deployable from this repository.

### Out of scope (explicit)

- **No OCR.** Hand-written scans, image-only PDFs, and tables are not
  ingested. Only Markdown, plain text, and textual PDFs are accepted.
- **No complex table parsing.** Tables, charts and multimodal figures are
  not parsed, normalised, or rendered.
- **No analytics or continuous monitoring.** No dashboards, no observability
  backplane, no SLA/alerting wiring.
- **No managed hosting.** No public URL, no TLS termination, no SaaS
  multi-tenancy, no billing. Bring-up is local-only (`docker compose up`).
- **No perfect-accuracy promise.** Embeddings are lossy; the assistant may
  refuse correctly and may still get a partially-supported answer wrong.
  Every answer carries the citations it was grounded in — read them.
- **No large-language-model fine-tuning.** This stack is an integration
  harness, not a model-training pipeline.
- **No live external services.** The embedding adapter is a deterministic stub
  in this release. Live integration with a vendor can be wired in via
  `EMBEDDING_STUB=false`, but the repository never ships vendor credentials.
- **No 24/7 operation.** This is a reproducible demonstration, not a
  production service.

### In scope

- Docker Compose contract with `db`/`api`/`ui`/`test`.
- `/healthz`, `/readyz`, `/v1/identity`, `/v1/collections`,
  `/v1/ingest`, `/v1/query`, `/v1/citations/{chunk_id}`,
  `/v1/embeddings` stub.
- Embedding adapter interface + deterministic stub.
- pgvector extension enabled + skeleton tables.
- Static UI shell plus a production-ready interface with configurable
  identity, three explicit answer states (answered/refused/error),
  citation rendering, workspace switcher, and auth-token UI.
- pytest + Playwright/Chromium test image (unit, integration, acceptance,
  security, **E2E UI** in `tests/e2e/`).
- Audit logger + redaction smoke tests.
- Auth gate (off by default) + smoke tests + E2E auth surface.
- Retention column + documented `RETENTION_DAYS`.
- Proof corpus + 16-question acceptance run + gaps report.
- This README.

Handoff documentation, smoke sweep, and the final scope report are part of
this release.

## Handoff — operation & maintenance (REQ-009)

### Backup & restore

The pgvector volume is the only stateful surface. Two artefacts are
captured by `scripts/backup-restore.sh`: a `pg_dump --format=custom`
archive of the live database and a `tar.gz` of the on-disk corpus
(`data/corpus`). Each backup lives in a timestamped directory under
`./backups/` with a sidecar `SHA256SUMS` so the next backup can be
compared against it.

```bash
./scripts/backup-restore.sh backup                    # writes ./backups/<UTC-timestamp>/
./scripts/backup-restore.sh restore ./backups/<dir> --confirm
```

`restore` drops the `public` schema, recreates it, and pipes the dump
back through `pg_restore --single-transaction` so a partial restore
fails closed. The corpus is re-materialised from the tarball if one is
present. The script requires `--confirm` so a stray invocation cannot
wipe production data.

### Updating the corpus

1. Drop new Markdown / text / textual-PDF files into `data/corpus/`.
2. Rebuild and bring the stack back up: `docker compose build --pull api && docker compose up -d --wait`.
3. Re-run the proof to refresh `proof/results.json` and `proof/results.md`:
   `./scripts/run-proof.sh`.
4. Review `proof/gaps.md` and update it if the new documents close
   any open refusal topic — `verify-proof-artifacts.sh` enforces that
   every corpus document appears in the source map.

The Proof corpus and the runtime corpus share the same files; the
proof runner re-ingests them in a clean collection every run, so a
broken document surfaces as an ingest error before it ever reaches
a user query.

### Switching the embedding provider

The provider is decoupled by `api/app/embeddings.py` (DEC-005). The
stub (`EMBEDDING_STUB=true`) is a deterministic local hash-to-vector
adapter used for tests and offline runs. To use a real OpenAI-compatible
provider:

```bash
# .env
EMBEDDING_STUB=false
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_API_KEY=<set by secret manager — never commit>
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536
```

Then rebuild the API image: `docker compose build --pull api && docker
compose up -d --wait`. The dimension column on `chunks` is created by
`ensure_schema()` based on `EMBEDDING_DIM`, so changing the value
without a fresh volume raises a startup error — that is intentional.

### Retention

`RETENTION_DAYS` declares the retention window for any audit / chat
records that land in the `audit_events` and `chat_messages` tables.
The default is `90`. **No automatic destructive job ships with this
package.** The shipped Compose file does not run any cron, systemd
timer or scheduled cleanup. The procedure for destructive retention
is manual and lives in `publication/RETENTION.md` — it requires a
backup, a row-count preview, a `BEGIN/ROLLBACK` dry-run, the literal
confirmation word `DELETE` and a post-delete backup. The audit mirror
is optional and is gated by `RETENTION_DAYS > 0` in the schema.

### Operational checklist

| Step                              | Command                                                                  |
|-----------------------------------|--------------------------------------------------------------------------|
| Bring the stack up                | `docker compose up -d --wait`                                            |
| Run the security smoke            | `docker compose run --rm test`                                           |
| Run the E2E UI smoke (REQ-006)    | `./scripts/smoke-ui.sh`                                                  |
| Run the full sweep                | `./scripts/test-all.sh`                                                  |
| Re-run the proof + acceptance run | `./scripts/run-proof.sh && ./scripts/verify-proof-artifacts.sh`          |
| Verify the handoff contract       | `./scripts/verify-handoff.sh`                                            |
| Verify the scope contract         | `./scripts/verify-scope.sh`                                              |
| Take a backup                     | `./scripts/backup-restore.sh backup`                                     |
| Restore from a backup             | `./scripts/backup-restore.sh restore ./backups/<dir> --confirm`          |
| Tear it all down (DESTRUCTIVE)    | `docker compose down -v`                                                 |

## Troubleshooting

- **`docker compose config --quiet` fails** — usually a missing `.env`.
  Copy `.env.example` and retry.
- **`api` keeps restarting** — check `docker compose logs api`. The healthcheck
  is `curl http://127.0.0.1:8000/healthz`; if it never comes up, the FastAPI
  container probably crashed at startup (read the log).
- **`pgvector extension missing`** — the `db` image must be `pgvector/pgvector:pgXX`
  (not stock `postgres:pgXX`). The compose file pins `pgvector/pgvector:pg16`;
  if you swap images, also re-run `db/init.sql` or call `ensure_schema()`.
- **`/v1/query` always returns `insufficient_evidence`** — check the
  `RETRIEVAL_MIN_SCORE`/`threshold` in the API response. The acceptance
  corpus is intentionally narrow; broaden `data/corpus/` and re-run
  `./scripts/run-proof.sh` to refresh `proof/gaps.md`.
- **`AUTH_ENABLED=true` returns 401 even with the right token** —
  verify `AUTH_TOKEN` matches between `.env`, `docker-compose.yml`
  interpolation, and the in-container process. The audit log line for
  the 401 will say `denied: <reason>` with the redacted token shape.
- **`test` image pulls slowly on first build** — Chromium is ~150 MB and is
  baked into the upstream Playwright image; subsequent builds reuse the
  layer.
- **Port `8080` in use** — set `UI_PORT` in `.env` to any free host port.
- **`backup-restore.sh restore` aborts** — the script requires `--confirm`
  and a valid path under `./backups/`. Re-run with both: e.g.
  `./scripts/backup-restore.sh restore ./backups/20260815T123000Z --confirm`.
- **Changing `EMBEDDING_DIM` does not change results** — the column is
  created by `ensure_schema()` only on a fresh volume. Re-create the
  volume with `docker compose down -v` (DESTRUCTIVE) and bring the
  stack back up.

## Final scope report (REQ-010)

The repository implements REQ-001..009 and explicitly disclaims REQ-010
limits (see *Out of scope* above). Two caveats to keep in mind:

- **Q13 drift residual (1/16 questions).** Q13 ('Copa America 2024') unexpectedly returned status=answered with best_score=0.2977 ABOVE the retrieval threshold of 0.20. The corpus does not contain sports content; the drift is a known stub-embedding limitation documented in proof/gaps.md. The verifier (./scripts/verify-proof-artifacts.sh) tolerates the 1/16 (6.25%) drift; the acceptance envelope allows up to 20% drift. Re-running ./scripts/run-proof.sh deterministically reproduces the same drift because the stub embeddings are hash-stable.
- **Token in `localStorage` is a static-gate tradeoff.** The UI persists
  the bearer token in `localStorage` so a single-tab refresh keeps the
  authenticated state. This is the right tradeoff for a static-token
  gate over `localhost`; a real production deployment should replace
  `api/app/auth.py` with a proper IdP (OIDC / OAuth2) and move the
  token out of `localStorage` (e.g. `HttpOnly` cookie + CSRF token).
  The gate is isolated to one module so the swap is mechanical.

## Portfolio case

A sanitized, local portfolio case study is available at
[`publication/portfolio/`](publication/portfolio/) — it is a
self-contained set of documents (problem statement, target public,
solution, architecture, stack, decisions, security, verified
results, honest limitations, how to run) plus reusable short
copy and a navigable index. The case is sanitized: it does not
refer to internal identities, internal paths, secrets, or
internal platforms. Visit [`publication/portfolio/`](publication/portfolio/)
to read the case study, [`publication/portfolio/SHORT-COPY.md`](publication/portfolio/SHORT-COPY.md)
for paste-ready paragraphs, and [`publication/portfolio/assets/`](publication/portfolio/assets/)
for the review-ready screenshots.

## License

This project is licensed under the **MIT License** — see the
[`LICENSE`](./LICENSE) file for the full text.

Copyright (c) 2026 Felipe Harms.
