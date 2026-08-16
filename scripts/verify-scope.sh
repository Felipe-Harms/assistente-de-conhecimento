#!/usr/bin/env bash
# REQ-010 — scope verifier. Inspects the repository and asserts that the
# explicit OUT-OF-SCOPE contract is honoured:
#
#   - README has an `Out of scope` section covering every limit the
#     contract lists (no OCR, no complex tables, no analytics, no managed
#     hosting, no perfect-accuracy promise, no LLM fine-tuning, no live
#     external services, no 24/7 operation).
#   - The Proof corpus (the repository gap report) lists the topics the assistant
#     is expected to refuse on, so the acceptance run can prove refusal.
#   - The retention column is wired (`audit_events`) but never auto-runs
#     a destructive job — `RETENTION_DAYS` is a documented knob.
#   - No vendor credentials are committed.
#   - The README has a `License` placeholder (All rights reserved) so
#     downstream consumers do not assume a permissive licence.
#
# Each check is independent and exits non-zero on the first failure.

set -euo pipefail

cd "$(dirname "$0")/.."

red()   { printf '\033[31m%s\033[0m\n' "$*" >&2; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
note()  { printf '\033[36m%s\033[0m\n' "$*"; }

fail=0

check_phrase() {
    local file="$1" phrase="$2"
    if ! grep -qF "$phrase" "$file"; then
        red "$file missing phrase: $phrase"
        fail=1
    else
        note "OK: '$phrase' present in $file"
    fi
}

echo "== README explicit limits =="
check_phrase README.md "No OCR"
check_phrase README.md "No complex table parsing"
check_phrase README.md "No analytics or continuous monitoring"
check_phrase README.md "No managed hosting"
check_phrase README.md "No perfect-accuracy promise"
check_phrase README.md "No large-language-model fine-tuning"
check_phrase README.md "No live external services"
check_phrase README.md "No 24/7 operation"
check_phrase README.md "Out of scope"

echo "== License placeholder =="
check_phrase README.md "License"

echo "== Proof gaps document refusal surface =="
if [[ ! -f the repository gap report ]]; then
    red "the repository gap report missing"
    fail=1
else
    note "the repository gap report present"
fi

echo "== No vendor credentials committed =="
# Detect real-looking vendor secrets while tolerating placeholder values
# of the form `sk-replace-me-...` / `sk-EXAMPLE-...` that the templates
# ship with. A real key matches `sk-` followed by at least 20 chars that
# do NOT include `replace-me`, `EXAMPLE`, `placeholder`, or `changeme`.
hits="$(set +e
       grep -RIEoh "sk-[A-Za-z0-9_-]{20,}" \
            --include='*.py' --include='*.md' --include='*.yml' \
            --include='*.env*' --include='*.json' --include='*.sh' . 2>/dev/null \
       | grep -viE 'sk-(replace-me|EXAMPLE|placeholder|changeme|sample|dummy)'
       true)"
if [[ -n "$hits" ]]; then
    red "vendor-shaped secret detected:"
    printf '%s\n' "$hits" | sed 's/^/    /' >&2
    fail=1
else
    note "no committed vendor credentials (placeholders OK)"
fi
if [[ -f .env && -s .env ]]; then
    # The .env file exists locally (gitignored). It is allowed, but must
    # be in .gitignore so it cannot be committed by accident.
    if ! grep -qF '.env' .gitignore; then
        red ".env exists but is not listed in .gitignore"
        fail=1
    else
        note ".env present and gitignored"
    fi
fi

echo "== Retention knob is documented, not auto-destructive =="
check_phrase README.md "RETENTION_DAYS"
check_phrase .env.example "RETENTION_DAYS"
# Make sure no scheduled cleanup jobs are wired into the compose stack.
if grep -qE "DELETE FROM audit_events|cron|cleanup" docker-compose.yml api/Dockerfile; then
    red "compose/api wired an automatic destructive retention job (out of scope)"
    fail=1
else
    note "no automatic destructive retention in compose/api"
fi

if (( fail )); then
    red "verify-scope: FAILED"
    exit 1
fi
green "verify-scope: OK"