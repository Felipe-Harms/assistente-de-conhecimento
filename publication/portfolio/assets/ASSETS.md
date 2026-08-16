# Portfolio Assets

Review-ready screenshots from the local gallery, renamed for
sanitized reuse in the portfolio case study. The screenshots are
captured deterministically against the shipped corpus and the
deterministic stub embedding adapter — re-running
`scripts/run-demo.sh` regenerates byte-different but visually
identical PNGs.

## Inventory

| File | Source | What it shows |
|------|--------|---------------|
| `idle.png` | `gallery/01-idle.png` | Brand surface on first load. Auth pill muted, citation card empty, the workspace switcher is collapsed. |
| `answered.png` | `gallery/02-answered.png` | An on-topic question with a citation-backed response. The citations appear as clickable cards below the answer; the inline `[N]` markers anchor-link to the matching card. |
| `refused.png` | `gallery/03-refused.png` | An off-topic question returning `reason=insufficient_evidence` with the computed `best_score` and `threshold` visible for audit. |
| `error-banner.png` | `gallery/04-auth-error.png` | The friendly error banner with a primary action button (the simulated 401 case shows the *"Open token settings"* action). |

## How to regenerate

```bash
# 1. Bring the stack up
docker compose up -d --wait

# 2. Regenerate the gallery
./scripts/run-demo.sh

# 3. Re-capture the references (only after a deliberate change)
GALLERY_RECAPTURE=1 ./scripts/verify-gallery.sh

# 4. Refresh the portfolio assets
cp gallery/01-idle.png       publication/portfolio/assets/idle.png
cp gallery/02-answered.png   publication/portfolio/assets/answered.png
cp gallery/03-refused.png    publication/portfolio/assets/refused.png
cp gallery/04-auth-error.png publication/portfolio/assets/error-banner.png
```

## Provenance

The screenshots are produced inside the test container, which runs
the Playwright Python client against Chromium. The UI is loaded at
`http://ui:80?workspace=<gallery-uuid>` so each capture is isolated.
No real customer data, no third-party branding, and no embedded
credentials are present in any PNG. The screenshots are an empty
UI surface on the local stub.
