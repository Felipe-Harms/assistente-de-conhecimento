# Index — Portfolio Case Sections

> A navigable index of every section in [CASE.md](CASE.md). Each row points at the heading and offers a one-line summary so you can scan the document without scrolling.

🇬🇧 **This is the English documentation.** [Ler em português (Brasil) →](./INDEX.md)

## Sections

| # | Section | One-line summary |
|---|---------|------------------|
| 1 | [Problem](CASE.md#1-problem) | Trust, refusal, audit, reproducibility, and deployment friction — the unspoken trade-offs that separate a demo from a delivery. |
| 2 | [Target public](CASE.md#2-target-public) | Small-to-mid delivery teams with a curated corpus and no managed backend available. |
| 3 | [Solution](CASE.md#3-solution) | A four-service local stack that surfaces three honest answer states (`answered`, `refused`, `error`) and an actionable empty state. |
| 4 | [Architecture and stack](CASE.md#4-architecture-and-stack) | nginx + FastAPI + Postgres/pgvector + Playwright, with a one-line justification for each choice. |
| 5 | [Key decisions](CASE.md#5-key-decisions) | Three honest states, citations as first-class, refusal as a feature, no vendor lock-in, reproducible acceptance, manual retention. |
| 6 | [Security and isolation](CASE.md#6-security-and-isolation) | Auth gate, Pydantic validation, structured audit log, secret-scanning, network isolation, and the localStorage tradeoff. |
| 7 | [Verifiable results](CASE.md#7-verifiable-results) | 70 + 20 + 8 + 24 = 122 tests green on a fresh clone, plus the documented Q13 drift (1/16 within the 20 % budget). |
| 8 | [Honest limitations](CASE.md#8-honest-limitations) | No real-world knowledge, no OCR, no perfect accuracy, no live services, auth-off by default, localStorage, stub embedding, no hosted mode, no SLA, no advanced reasoning. |
| 9 | [How to run the demo](CASE.md#9-how-to-run-the-demo) | `git clone → cp .env.example .env → docker compose up -d --wait → curl` and the canonical closeout chain. |
| 10 | [Stack refresh and embedding switch](CASE.md#10-stack-refresh-and-embedding-switch) | Swap the stub for a real OpenAI-compatible provider via configuration, not code. |
| 11 | [Source-of-truth pointers](CASE.md#11-source-of-truth-pointers) | Where to look in the repository for each claim made in the case study. |

## Reusable short copy

| Block | Where to use it |
|-------|-----------------|
| [One-paragraph summary](SHORT-COPY.md#1-the-one-paragraph-summary) | Portfolio landing page, "about the project" paragraph. |
| [Three-sentence elevator pitch](SHORT-COPY.md#2-the-three-sentence-elevator-pitch) | Cold outreach, résumé headline, conference bio. |
| [Trust-and-trade-off block](SHORT-COPY.md#3-the-trust-and-trade-off-block) | Buyer-facing security review, due-diligence questionnaire. |
| [Specific-results block](SHORT-COPY.md#4-the-specific-results-block) | Pre-sales deck, proposal annex, "what does the test suite actually prove?" question. |
| ["Who is this for" paragraph](SHORT-COPY.md#5-the-who-is-this-for-paragraph) | Audience-scoping section, scope-of-work narrative. |

## Companion files

| File | Purpose |
|------|---------|
| [README.md](README.md) | Entry point — what this directory is, how to read it, how the case is kept honest. |
| [CASE.md](CASE.md) | The full case study. |
| [SHORT-COPY.md](SHORT-COPY.md) | Reusable short paragraphs. |
| [INDEX.md](INDEX.md) | This file — navigable index. |
| [assets/](assets/) | Review-ready screenshots from the gallery. |

---

🇬🇧 **This is the English documentation.** [Ler em português (Brasil) →](./INDEX.md)
