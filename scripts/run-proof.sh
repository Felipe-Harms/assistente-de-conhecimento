#!/usr/bin/env bash
# REQ-005 orchestrator: ingest corpus, run questions, write proof artifacts.
#
# This script delegates the heavy lifting to scripts/run_proof.py, which
# runs *inside* the test container so it can hit the `api` service on the
# shared `backend` docker network. The wrapper:
#   1. Forces a fresh `upworkkb-test` build so the latest run_proof.py and
#      corpus files are baked in.
#   2. Runs the proof runner, capturing stdout/stderr.
#   3. Verifies the artifacts it produced.
#
# Exits non-zero if the runner fails or if the verifier rejects the
# artifacts (REQ-005 acceptance contract).

set -euo pipefail

cd "$(dirname "$0")/.."

# Build so any change to scripts/ or data/ is reflected in the image.
docker compose build --pull test >/dev/null

docker compose run --rm \
    -e CORPUS_DIR=/srv/data/corpus \
    -e PROOF_DIR=/srv/repo/proof \
    -e API_BASE=http://api:8000 \
    test python /srv/repo/scripts/run_proof.py

./scripts/verify-proof-artifacts.sh