# Test image — Python + Playwright + Chromium pre-installed (REQ-006 prep).
# Base image already includes Chromium and the headless shell at
# `/ms-playwright`; we only add the Python tooling we actually use.

FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Playwright env — matches chromium rev 1148 baked into the base image.
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

WORKDIR /srv

# Test-only Python deps. Includes the api runtime so security tests can
# import `app.main` directly (the api source is mounted at /srv/api below).
COPY tests/requirements.txt /srv/tests/requirements.txt
RUN pip install --no-cache-dir -r /srv/tests/requirements.txt

# Source layout — api lives at /srv/api, tests live at /srv/tests. The
# repo-level files (.env.example, .gitignore, README.md, docker-compose.yml,
# ui/, db/, scripts/) are mirrored under /srv/repo so the secrets scanner
# can inspect everything that ships in the repository.
COPY api /srv/api
COPY tests /srv/tests
COPY .gitignore .env.example README.md docker-compose.yml /srv/repo/
COPY ui /srv/repo/ui
COPY db /srv/repo/db
COPY scripts /srv/repo/scripts
COPY data /srv/repo/data
COPY data /srv/data
# Mirror the build-time Dockerfile into the image so the acceptance
# contract test (tests/acceptance/test_proof_build_contract.py) can read
# it back at runtime and assert that no `COPY proof …` line ever
# regresses into the image.
COPY test/Dockerfile /srv/repo/test/Dockerfile
# NOTE: `proof/` is intentionally NOT baked into the image. It is a
# runtime artifact produced by scripts/run_proof.py, and the docker
# compose `test` service mounts the host's ./proof into /srv/repo/proof
# so the verifier on the host can read the generated artifacts after
# `scripts/run-proof.sh` runs.

# Both /srv/api (so `from app.main import ...` works) and /srv (so
# `from tests.security.test_auth import ...` works) need to be on the path.
ENV PYTHONPATH=/srv/api:/srv

# Tests live at /srv/tests/security/...; from /srv, they resolve as
# tests/security — same path the verifier uses. `run --rm test pytest
# tests/integration` works the same way.
WORKDIR /srv

CMD ["pytest", "-q", "tests/security", "-k", "not slow"]
