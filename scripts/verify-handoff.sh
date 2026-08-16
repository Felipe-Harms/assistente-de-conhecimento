#!/usr/bin/env bash
# REQ-009 — handoff verifier. Inspects the repository and prints the
# handoff contract surface area that operators rely on:
#
#   - Architecture diagram (README)
#   - Configuration table (.env.example)
#   - Backup & restore script (scripts/backup-restore.sh)
#   - Retention policy (RETENTION_DAYS documented)
#   - Embedding-provider swap path (DEC-005)
#   - Corpus update path (data/corpus + scripts/run-proof.sh)
#   - Smoke + full-sweep entry points (scripts/smoke-ui.sh, scripts/test-all.sh)
#   - Troubleshooting section (README)
#   - Scope & limits section (README)
#   - Teardown command documented
#
# Each check is independent. The script exits non-zero the first time any
# required item is missing — so a missing file or a stale section is
# loud and obvious. Intentionally shell-only so it runs on the host
# without docker.

set -euo pipefail

cd "$(dirname "$0")/.."

red()   { printf '\033[31m%s\033[0m\n' "$*" >&2; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
note()  { printf '\033[36m%s\033[0m\n' "$*"; }

fail=0
check_file() {
    local path="$1"
    if [[ ! -f "$path" ]]; then
        red "missing required file: $path"
        fail=1
    else
        note "found $path"
    fi
}

check_exec() {
    local path="$1"
    if [[ ! -x "$path" ]]; then
        red "not executable: $path"
        fail=1
    else
        note "executable $path"
    fi
}

check_section() {
    local file="$1" section="$2"
    if ! grep -qF "$section" "$file"; then
        red "section '$section' missing from $file"
        fail=1
    else
        note "section present: $section"
    fi
}

check_env_var() {
    local var="$1"
    if ! grep -qE "^${var}=" .env.example; then
        red ".env.example missing variable: $var"
        fail=1
    else
        note ".env.example exposes $var"
    fi
}

echo "== Architecture =="
check_file README.md
check_section README.md "Architecture"
check_section README.md "Configuration"

echo "== Configuration surface =="
check_file .env.example
for v in POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB DATABASE_URL \
         AUTH_ENABLED AUTH_TOKEN EMBEDDING_BASE_URL EMBEDDING_API_KEY \
         EMBEDDING_MODEL EMBEDDING_DIM EMBEDDING_STUB RETENTION_DAYS \
         APP_BRAND_NAME APP_TAGLINE APP_ACCENT_COLOR APP_LOGO_URL APP_FOOTER_NOTE \
         UI_PORT; do
    check_env_var "$v"
done

echo "== Operational scripts =="
check_exec scripts/smoke-ui.sh
check_exec scripts/test-all.sh
check_exec scripts/run-proof.sh
check_exec scripts/verify-proof-artifacts.sh
check_exec scripts/backup-restore.sh

echo "== Backup & restore contract =="
check_section README.md "Backup"
check_section .env.example "RETENTION_DAYS"

echo "== Corpus update path =="
check_section README.md "Architecture"
check_section README.md "Quick Start"
if [[ ! -d data/corpus ]]; then
    red "missing data/corpus directory"
    fail=1
else
    note "corpus directory present: data/corpus"
fi

echo "== Provider swap path =="
check_section README.md "Embedding adapter"
check_section .env.example "EMBEDDING_STUB"

echo "== Operation & troubleshooting =="
check_section README.md "Quick Start"
check_section README.md "Troubleshooting"
check_section README.md "Scope & limits"

echo "== Teardown command =="
if ! grep -qE "docker compose down -v" README.md; then
    red "README missing teardown command"
    fail=1
else
    note "teardown command documented in README"
fi

echo "== Smoke + full sweep =="
check_exec scripts/smoke-ui.sh
check_exec scripts/test-all.sh

if (( fail )); then
    red "verify-handoff: FAILED"
    exit 1
fi
green "verify-handoff: OK"