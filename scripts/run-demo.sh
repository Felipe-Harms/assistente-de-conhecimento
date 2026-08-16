#!/usr/bin/env bash
# REQ-003 — deterministic demo entry point.
#
# Two modes:
#   ./scripts/run-demo.sh           capture gallery screenshots + write JSON
#   ./scripts/run-demo.sh --verify  run the API-level verifier (no screenshots)
#
# The capture mode runs INSIDE the test container, where Playwright +
# Chromium are pre-installed and the API/UI services are reachable at
# the docker service hostnames. The script copies the demo Python
# files into the running test container, runs them, then copies the
# PNG screenshots out into ./gallery/. The verify mode runs purely on
# the host and does not need the test container at all.
#
# Both modes are deterministic — the on-topic / off-topic / auth-error
# states are pinned to fixed questions in the shipped corpus, so the
# outcome does not depend on the host clock, RNG or network.

set -euo pipefail

cd "$(dirname "$0")/.."

red()   { printf '\033[31m%s\033[0m\n' "$*" >&2; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
note()  { printf '\033[36m%s\033[0m\n' "$*"; }

verify_mode=0
if [[ "${1:-}" == "--verify" ]]; then
    verify_mode=1
fi

# Stack must be up for either mode. The verify mode hits the API via
# the host port; the capture mode runs inside the test container
# against the docker service hostnames.
if ! docker compose ps --status running 2>/dev/null | grep -qE 'upworkkb-(api|test|ui)\s' ; then
    note "stack not up — bringing it up first"
    docker compose up -d --wait
fi

if (( verify_mode )); then
    note "verify mode: API-level checks only"
    python3 scripts/_demo_verify.py
    exit $?
fi

# Capture mode.
mkdir -p gallery

# Stage the demo scripts inside the test container. The canonical
# service container is `upworkkb-test`. We never use a leftover
# one-off container from a previous `docker compose run --rm test`
# — those have stale mounts and would fail to find /srv/data/corpus.
TEST_CONTAINER="upworkkb-test"
if ! docker ps --format '{{.Names}}' | grep -qx "$TEST_CONTAINER"; then
    red "container $TEST_CONTAINER is not running; run docker compose up -d first"
    exit 1
fi
note "test container: $TEST_CONTAINER"

docker cp scripts/_demo_capture.py "${TEST_CONTAINER}:/srv/_demo_capture.py"
trap 'docker exec "${TEST_CONTAINER}" rm -f /srv/_demo_capture.py 2>/dev/null || true; docker exec "${TEST_CONTAINER}" rm -rf /srv/_gallery_staging 2>/dev/null || true' EXIT

# Run inside the test container. Output goes to stdout; the JSON
# payload is delimited so we can extract it cleanly.
note "running Playwright capture inside test container"
set +e
docker exec -i "${TEST_CONTAINER}" python3 /srv/_demo_capture.py /srv/_gallery_staging
rc=$?
set -e
if (( rc != 0 )); then
    red "demo capture failed (exit=$rc)"
    exit "$rc"
fi

# Pull the PNGs out of the container.
note "extracting PNGs to ./gallery/"
docker exec "${TEST_CONTAINER}" ls -1 /srv/_gallery_staging
docker cp "${TEST_CONTAINER}:/srv/_gallery_staging/." ./gallery/

# Verify the PNGs are real (header sanity).
note "verifying PNG headers"
fail=0
for f in gallery/*.png; do
    [[ -s "$f" ]] || { red "missing/empty: $f"; fail=1; continue; }
    if ! head -c 8 "$f" | grep -q "PNG"; then
        red "not a valid PNG: $f"
        fail=1
    fi
done
if (( fail )); then
    red "gallery capture produced invalid files"
    exit 1
fi

# Print a summary.
echo
echo "gallery/ now contains:"
ls -la gallery/*.png 2>/dev/null || ls -la gallery/

green "demo capture complete"
echo
echo "Run \`./scripts/verify-gallery.sh\` to validate the manifest."