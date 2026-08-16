# Portfolio Case — Local-First Knowledge Assistant

> A reproduction-ready, citation-grounded answer service that runs on a single `docker compose up` and never touches a credit card. Every answer is grounded in the operator's own corpus, refuses honestly when the evidence is thin, and ships with a deterministic test suite that proves the contract.

🇬🇧 **This is the English documentation.** [Ler em português (Brasil) →](./README.md)

## Start here

- **[CASE.md](CASE.md)** — the full case study: problem, target public, solution, architecture, stack, decisions, security, verified results, honest limitations, and how to run the demo.
- **[SHORT-COPY.md](SHORT-COPY.md)** — three reusable paragraphs you can paste into a proposal, a resume bullet, or a portfolio site.
- **[INDEX.md](INDEX.md)** — a navigable index of every section in the case study, with the section header and a one-line summary.
- **[assets/](assets/)** — review-ready screenshots from the gallery: idle, answered, refused, and the friendly error banner.

## What this case is not

- It is **not** the source of the code. The code lives in the repository root and in `ui/`, `api/`, `db/`, `tests/`, and `scripts/`.
- It is **not** a marketing page. The verified results and the honest limitations are mandatory sections, not optional.
- It is **not** an external publication. Nothing here is posted to a third-party platform; this is a local artifact that visitors can browse alongside the code.

## How the case is kept honest

- The case study cites the test counts (`70 security + 20 integration + 8 acceptance + 24 end-to-end = 122`) verbatim from the reproducible test suites.
- The Q13 drift ("Who won the 2024 Copa America final?") is declared as a known limitation, because the deterministic stub embedding lifts a borderline fragment above the retrieval threshold. The drift is documented in the repository gap report and is preserved verbatim in the repository.
- The local-only posture is declared explicitly: no hosted mode, no SLA, no 24/7 monitoring, no public endpoint.
- The token-in-localStorage tradeoff is declared as a deliberate tradeoff of the static-token gate, not as a recommended pattern for production deployment.

## How to reproduce the results

The case study's verifiable numbers come from these commands:

```bash
# Bring up the stack
docker compose up -d --wait

# Run the full test sweep
docker compose run --rm test pytest -q tests/security
docker compose run --rm test pytest -q tests/integration
docker compose run --rm test pytest -q tests/acceptance
./scripts/smoke-ui.sh

# Canonical closeout chain
./scripts/test-publication.sh
```

The same chain runs in CI and on a fresh clone. There is no manual step between the commands and the verifiable numbers quoted in this case study.

## Bilingual documentation

This portfolio is published in Brazilian Portuguese as the primary presentation, with English clearly accessible:

- **Brazilian Portuguese:** `README.md`, `CASE.md`, `INDEX.md`, `SHORT-COPY.md`.
- **English:** `README.en.md`, `CASE.en.md`, `INDEX.en.md`, `SHORT-COPY.en.md`.

Technical identifiers (env names, API endpoints, function/class names, SQL, Docker services, JS identifiers) remain in English to preserve contracts.

---

🇬🇧 **This is the English documentation.** [Ler em português (Brasil) →](./README.md)
