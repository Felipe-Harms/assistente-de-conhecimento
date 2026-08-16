🇬🇧 **This is the English documentation.** [Ler em português (Brasil) →](./README.md)

# Knowledge Assistant

A local, Docker-Compose-first knowledge assistant that grounds answers in a curated corpus and refuses when the evidence is insufficient. Built as a proof/production demonstrator on synthetic and openly licensed material.

> **End-to-end UI live.** A static bundle (nginx) consumes a configurable brand surface from `GET /v1/identity`, lets the operator pick a collection + workspace, submits questions through `POST /v1/query`, and renders one of three honest states — *answered* (with citations), *refused* (`insufficient_evidence`), or *error*. Auth is configurable via `AUTH_ENABLED=true`; when on, the UI shows a bearer-token input and forwards `Authorization: Bearer …` on every request. Every request is audited in structured JSON via `app.audit`.

---

## Overview

- **Goal.** A reproducible local stack: a FastAPI service, a static UI, and a PostgreSQL+pgvector store, plus a `test` image that runs `pytest` (with Playwright + Chromium driving the end-to-end UI in `tests/e2e/`).
- **Non-goal.** Not a SaaS, not a public deployment, not a model fine-tuning pipeline. See *Scope & limits* below.
- **Stack.** Python 3.12 (api/test), nginx (ui), PostgreSQL 16 with pgvector (db). `docker compose` is the only supported way to bring it up.

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

# Run the E2E UI smoke — needs the stack up:
./scripts/smoke-ui.sh

# Run the full sweep: security + integration + acceptance + E2E + proof:
./scripts/test-all.sh
```

## Architecture

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│      ui      │    │      api     │    │      db      │
│  (nginx)     │◄──►│  (FastAPI)   │◄──►│  PostgreSQL  │
│  HTML/CSS/JS │    │  Python 3.12 │    │   +pgvector  │
└──────────────┘    └──────────────┘    └──────────────┘
                            ▲
                            │
                      ┌──────────────┐
                      │     test     │
                      │  pytest +    │
                      │  Playwright  │
                      └──────────────┘
```

- **ui/** — static bundle served by nginx. Configurable at runtime via `GET /v1/identity`.
- **api/** — FastAPI Python 3.12 service with asyncpg + SQLAlchemy + structured logs. Endpoints: `GET /v1/identity`, `GET /v1/collections`, `POST /v1/query`, `POST /v1/ingest`.
- **db/** — PostgreSQL 16 with pgvector. Schema and HNSW index initialized in `db/init.sql`.
- **test/** — pytest image with Playwright + Chromium for E2E UI tests.

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/v1/identity` | Returns brand, auth, and identity configuration. |
| `GET`  | `/v1/collections?workspace=<id>` | Lists available collections in the workspace. |
| `POST` | `/v1/query` | Submits a question; returns `answered` (with citations) or `refused`. |
| `POST` | `/v1/ingest` | Ingests a document (multipart) into a collection. |
| `GET`  | `/healthz` | API health probe. |
| `GET`  | `/healthz-ui` | UI health probe (via nginx). |

All endpoints under `/v1/*` require `Authorization: Bearer <token>` when `AUTH_ENABLED=true`.

## Configuration

Environment variables are read exclusively from `.env` (see `.env.example`). Key variables:

- `AUTH_ENABLED` — when `true`, requires bearer token on requests.
- `AUTH_TOKEN` — pre-shared bearer token.
- `EMBEDDING_STUB` — when `true`, uses deterministic local embedding (default); when `false`, uses OpenAI API.
- `RETRIEVAL_MIN_SCORE` — cosine similarity threshold to accept an answer.
- `UI_PORT` — port for the nginx UI (default `8080`).

## Security

- **Bearer token.** When `AUTH_ENABLED=true`, all API requests require `Authorization: Bearer <token>`.
- **Audit.** Each request is logged in structured JSON via `app.audit`.
- **Validation.** Inputs are validated by Pydantic; malformed payloads return 422.
- **Secrets.** Never embedded in code; always via env + `.env` (gitignored).

See `tests/security/` for the security test suite.

## Tests

```bash
# Security + integration + acceptance (inside the test container):
docker compose run --rm test

# E2E UI smoke (requires stack up):
./scripts/smoke-ui.sh

# Full suite:
./scripts/test-all.sh
```

## Internationalization

The UI has built-in i18n:
- **Default:** Brazilian Portuguese — `pt-BR`.
- **Toggle:** click the "EN"/"PT" button in the header to switch.
- **Persistence:** the preference is saved in `localStorage`.

## License

MIT — see [LICENSE](./LICENSE). Copyright (c) 2026 Felipe Harms.

## Contributing

Issues and pull requests are welcome. For large changes, open an issue first to discuss the approach.

---

🇬🇧 **This is the English documentation.** [Ler em português (Brasil) →](./README.md)
