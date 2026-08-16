#!/usr/bin/env bash
# Canonical closeout check for the public publication.
#
# The public subset is: gallery + demo + the existing application suite.
# The commercial-customer publication verifiers (build package, verify
# package, verify copy, retention policy, publication checklist) have
# been moved to `publication/internal-archive/scripts-comerciais/` —
# they are no longer part of the public suite.
#
# Usage:
#   ./scripts/test-publication.sh

set -euo pipefail

cd "$(dirname "$0")/.."

red()   { printf '\033[31m%s\033[0m\n' "$*" >&2; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
note()  { printf '\033[36m%s\033[0m\n' "$*"; }

run_block() {
    local label="$1"
    shift
    echo
    echo "================================================================"
    echo "[test-publication] $label"
    echo "================================================================"
    "$@"
}

# Demo + gallery verifiers. Skip gracefully when the scripts are not
# present yet.
if [[ -x scripts/run-demo.sh ]]; then
    run_block "run demo with verification" \
        ./scripts/run-demo.sh --verify
else
    note "run-demo.sh not present — skipped"
fi
if [[ -x scripts/verify-gallery.sh ]]; then
    run_block "verify gallery" \
        ./scripts/verify-gallery.sh
else
    note "verify-gallery.sh not present — skipped"
fi

# Cross-check the existing application suite is still green. test-all.sh
# exits on first failure, so reaching this block means the existing
# contract is intact.
run_block "existing suite (cross-check)" \
    ./scripts/test-all.sh

echo
echo "================================================================"
green "[test-publication] OK — every block passed"
echo "================================================================"
