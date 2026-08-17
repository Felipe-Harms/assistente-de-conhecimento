"""Regression test for the REQ-005 proof/build cycle fix.

The proof/build cycle was structurally broken in two ways:

  1. ``test/Dockerfile`` did ``COPY proof /srv/repo/proof`` but
     ``proof/`` is gitignored and only generated at runtime by
     ``scripts/run_proof.py`` (chicken-and-egg: clean clones could not
     build the test image because the build context did not have
     ``proof/``).

  2. ``scripts/run_proof.py`` ran inside an ephemeral test container
     launched via ``docker compose run --rm test ...``. The test
     service had no volume mount on ``./proof``, so the artifacts the
     runner wrote to ``/srv/repo/proof`` inside the container were
     discarded with the container overlay. The verifier on the host
     (``scripts/verify-proof-artifacts.sh``) therefore always read an
     empty ``proof/`` and failed.

The fix (tracked in this contract):

  - Remove ``COPY proof /srv/repo/proof`` from ``test/Dockerfile``.
  - Add ``volumes: ['./proof:/srv/repo/proof']`` to the
    ``docker-compose.yml`` ``test`` service so runtime artifacts land
    on the host.
  - Track ``proof/.gitkeep``, ``proof/questions.json`` and
    ``proof/gaps.md`` in git; runtime-generated artifacts remain
    gitignored.
  - Add ``RETRIEVAL_MIN_SCORE`` to ``.env.example`` to keep docs in
    sync with the live API setting.

This test runs inside the test container (``docker compose run --rm
test pytest tests/acceptance``) and verifies the contract from the
container's point of view.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path("/srv/repo")
PROOF = REPO / "proof"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing required file inside container: {path}"
    return path.read_text()


def test_docker_compose_test_service_mounts_proof_into_container() -> None:
    """The volume mount on the test service is the data-escape hatch.

    Without it, scripts/run_proof.py writes to /srv/repo/proof inside
    an ephemeral container and the host's ./proof/ stays empty.
    """
    compose = _read(REPO / "docker-compose.yml")
    assert "./proof:/srv/repo/proof" in compose, (
        "docker-compose.yml must bind-mount ./proof into /srv/repo/proof "
        "on the test service so run_proof.py output survives the "
        "ephemeral `docker compose run --rm test` lifecycle."
    )


def test_gitignore_does_not_block_canonical_proof_files() -> None:
    """.gitignore must allow the tracked files in proof/.

    The contract is ``proof/*`` (ignore generated contents) with
    explicit allow-list for the canonical files. The OLD pattern was a
    bare ``proof/`` which made the directory completely invisible to
    fresh clones.
    """
    gi = _read(REPO / ".gitignore")
    # Bare `proof/` line would ignore the whole tree (old, broken pattern).
    # We accept either the absence of any proof/ entry or the new
    # pattern with explicit allow-list entries.
    bare_proof_ignore = any(
        line.strip() == "proof/" for line in gi.splitlines()
    )
    assert not bare_proof_ignore, (
        ".gitignore contains a bare `proof/` line; canonical files "
        "(questions.json, gaps.md, .gitkeep) would not be tracked."
    )
    # The allow-list must exist for every canonical file.
    for allow in ("!proof/.gitkeep", "!proof/questions.json", "!proof/gaps.md"):
        assert allow in gi, f".gitignore missing allow-list entry: {allow}"


def test_env_example_documents_retrieval_min_score() -> None:
    """The README documents RETRIEVAL_MIN_SCORE; .env.example must too."""
    env = _read(REPO / ".env.example")
    assert "RETRIEVAL_MIN_SCORE" in env, (
        ".env.example must document RETRIEVAL_MIN_SCORE — the README "
        "quick-start mentions it but the operator needs a concrete "
        "default value in the env template."
    )


def test_questions_json_is_valid_with_expected_metadata() -> None:
    """Canonical acceptance spec must parse and satisfy REQ-005 bounds.

    REQ-005 requires 10–20 questions with at least 8 positive and 2
    negative. The verifier (``scripts/verify-proof-artifacts.sh``)
    enforces those bounds.
    """
    qpath = PROOF / "questions.json"
    assert qpath.is_file(), (
        f"missing canonical acceptance spec: {qpath}. The proof runner "
        "reads this file inside the test container and the verifier "
        "enforces its metadata bounds."
    )
    payload = json.loads(qpath.read_text())
    assert "questions" in payload and "metadata" in payload, (
        "questions.json must have top-level `questions` and `metadata` "
        "keys consumed by scripts/verify-proof-artifacts.sh."
    )
    meta = payload["metadata"]
    for key in (
        "expected_question_count_min",
        "expected_question_count_max",
        "expected_positive_min",
        "expected_negative_min",
    ):
        assert key in meta, f"questions.json metadata missing key: {key}"
    qs = payload["questions"]
    lo, hi = meta["expected_question_count_min"], meta["expected_question_count_max"]
    assert lo <= len(qs) <= hi, (
        f"questions count {len(qs)} outside [{lo}, {hi}]"
    )
    pos = sum(1 for q in qs if q.get("category") == "positive")
    neg = sum(1 for q in qs if q.get("category") == "negative")
    assert pos >= meta["expected_positive_min"], (
        f"only {pos} positive questions; need >= "
        f"{meta['expected_positive_min']}"
    )
    assert neg >= meta["expected_negative_min"], (
        f"only {neg} negative questions; need >= "
        f"{meta['expected_negative_min']}"
    )
    # Every question must have an id, category and expected_status —
    # those are the fields the verifier checks against results.json.
    for q in qs:
        assert "id" in q and "category" in q and "expected_status" in q, (
            f"question missing required field: {q}"
        )


def test_gaps_md_is_present_and_substantive() -> None:
    """Canonical gaps document must exist and be more than a stub."""
    gpath = PROOF / "gaps.md"
    assert gpath.is_file(), f"missing canonical gaps document: {gpath}"
    text = gpath.read_text().strip()
    assert len(text) > 200, (
        "proof/gaps.md should be a real document explaining the demo "
        "scope and known limitations; the verifier requires it to be "
        "present and the README points operators at it."
    )


def test_proof_gitkeep_is_tracked() -> None:
    """Empty marker so the proof/ directory exists in fresh clones.

    Without this, a fresh clone has no proof/ directory at all and the
    docker-compose volume mount would create an empty one — breaking
    run_proof.py which expects to read proof/questions.json.
    """
    assert (PROOF / ".gitkeep").is_file(), (
        "proof/.gitkeep must be tracked so a fresh clone has a "
        "non-empty proof/ directory that satisfies the volume mount "
        "and provides questions.json to the proof runner."
    )


def test_test_dockerfile_does_not_copy_proof_into_image() -> None:
    """Build-time contract: the test image must not bake proof/ in.

    The Dockerfile is mirrored into the image at ``/srv/repo/test/Dockerfile``
    by a ``COPY test/Dockerfile /srv/repo/test/Dockerfile`` line in the
    Dockerfile itself. The previous broken Dockerfile had
    ``COPY proof /srv/repo/proof`` which failed in clean clones.
    """
    dockerfile = Path("/srv/repo/test/Dockerfile")
    assert dockerfile.is_file(), (
        f"test/Dockerfile missing from build context: {dockerfile}"
    )
    content = dockerfile.read_text()
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert not stripped.startswith("COPY proof "), (
            f"test/Dockerfile still bakes proof/ into the image at "
            f"build time: `{stripped}`. This regresses the clean-"
            f"install flow because proof/ is gitignored and only "
            f"generated at runtime by scripts/run_proof.py."
        )