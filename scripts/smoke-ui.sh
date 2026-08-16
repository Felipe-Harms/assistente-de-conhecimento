#!/usr/bin/env bash
# REQ-006 smoke — drive the running UI from the test container with
# Playwright/Chromium and assert the happy path + refusal + auth surface.
#
# The script assumes the four-service stack is already up
# (`docker compose up -d --wait`). It exits non-zero on any failure so
# CI/operators can chain it after `docker compose up -d --wait`.
#
# Usage:
#   ./scripts/smoke-ui.sh

set -euo pipefail

cd "$(dirname "$0")/.."

echo "[smoke-ui] verifying stack is up"
docker compose ps --services --status running | grep -Eq '^(api|ui|db)$' || {
    echo "stack not up — run 'docker compose up -d --wait' first" >&2
    exit 1
}

echo "[smoke-ui] running Playwright E2E suite"
docker compose run --rm \
    -e UI_URL=http://ui:80 \
    -e API_URL=http://api:8000 \
    test pytest -q tests/e2e

echo "[smoke-ui] OK"