#!/usr/bin/env bash
# REQ-008 / REQ-010 — full test sweep: security + integration + acceptance
# + proof verifier + UI smoke. Every block exits non-zero on failure; the
# outer script fails on the first non-zero so operators get a clear
# stopping point.
#
# Usage:
#   ./scripts/test-all.sh

set -euo pipefail

cd "$(dirname "$0")/.."

run_block() {
    local label="$1"
    shift
    echo
    echo "================================================================"
    echo "[test-all] $label"
    echo "================================================================"
    "$@"
}

run_block "docker compose config" \
    docker compose config --quiet

run_block "docker compose up -d --wait" \
    docker compose up -d --wait

run_block "security suite (REQ-007)" \
    docker compose run --rm test pytest -q tests/security

run_block "integration suite (REQ-002 / REQ-003 / REQ-006)" \
    docker compose run --rm test pytest -q tests/integration

run_block "acceptance suite (REQ-004)" \
    docker compose run --rm test pytest -q tests/acceptance

run_block "proof verifier (REQ-005)" \
    ./scripts/verify-proof-artifacts.sh

run_block "ui smoke (REQ-006)" \
    ./scripts/smoke-ui.sh

echo
echo "[test-all] OK — every block passed"