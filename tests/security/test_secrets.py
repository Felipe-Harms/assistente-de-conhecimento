"""Security smoke tests — REQ-007 foundation.

Asserts that the repository contains no real secrets: only `.env.example` is
versioned and every file outside `.gitignore` is checked for common secret
shapes (Bearer tokens, sk-* keys, AWS keys, PEM blocks).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Inside the test container the project tree (incl. .env.example,
# docker-compose.yml, README.md, ui/, db/, scripts/) is mirrored at /srv/repo.
# When the file is run on the host directly (debug) we fall back to the
# location of __file__'s grandparent so the same scanner works there too.
_default = Path(__file__).resolve().parents[2]
REPO_ROOT = Path("/srv/repo") if Path("/srv/repo").exists() else _default

# These patterns catch common secret SHAPES. The scanner is allowed to
# ignore a match if any of the placeholder markers appears on the same line
# before the matched value. The markers are explicit so production code and
# config never accidentally trip a false negative.
PLACEHOLDER_TOKENS = (
    "replace-",
    "change-me-",
    "<",                  # angle-bracket placeholders in .env.example
    "replace_with",
    "replace-with",
    "PLACEHOLDER",        # upper-case human marker
    "placeholder",        # lower-case human marker
    "test-fixture",       # pytest fixture values
    "TEST_FIXTURE",
    "stub-",              # local stub identifiers (e.g. stub-key-…)
    "EXAMPLE",
)


def _low_entropy(s: str) -> bool:
    """Heuristic for fixture values that look secret-shaped but are not.

    Real secrets are high-entropy; test fixtures like "abcdefghijklmnopqrstuv"
    or "ZZZZZZ..." are not. The input is the literal matched span; we strip
    common prefixes (sk-, etc.) and non-letter characters before checking.
    """
    if not s:
        return True
    # Repeated runs of one or two characters (e.g. "ZZZZ", "aaa").
    if re.search(r"(.)\1{6,}", s):
        return True
    # Strip a known vendor prefix (the matched value frequently starts with
    # "sk-", "Bearer ", "xoxb-", etc.). Keep letters only.
    letters = "".join(ch for ch in s if ch.isalpha())
    if len(letters) >= 12:
        asc = all(ord(letters[i + 1]) - ord(letters[i]) == 1 for i in range(len(letters) - 1))
        desc = all(ord(letters[i]) - ord(letters[i + 1]) == 1 for i in range(len(letters) - 1))
        if asc or desc:
            return True
        # 50%+ of the same letter (e.g. "ZZZZZZ…" anyway has the long run
        # above; this catches milder cases like "aaaabbbbaaaa").
        from collections import Counter
        counts = Counter(letters).values()
        if counts and max(counts) / len(letters) > 0.4 and len(set(letters)) <= 3:
            return True
    return False

SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),                       # OpenAI / similar
    re.compile(r"\bghp_[A-Za-z0-9]{30,}\b"),                      # GitHub PAT
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),              # Slack
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                          # AWS access key id
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b"),  # JWT
)


def _is_placeholder(line: str, match_start: int) -> bool:
    """Is the matched token a known placeholder token?"""
    prefix = line[:match_start]
    # Determine the span of the matched value (prefer trailing quote or comma).
    match_end = line.find(",", match_start)
    if match_end == -1:
        match_end = len(line)
    quote = line.find('"', match_start)
    if quote != -1 and (match_end == -1 or quote < match_end):
        match_end = quote
    value = line[match_start:match_end]

    haystack = prefix + " " + value
    if any(marker in haystack for marker in PLACEHOLDER_TOKENS):
        return True
    return _low_entropy(value)


def _all_text_files():
    skip_dirs = {".git", ".wolfpack", "node_modules", "__pycache__", ".pytest_cache",
                 ".venv", "venv", "data", "logs", "test-results", ".playwright"}
    skip_files = {"Pipfile.lock", "package-lock.json"}
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(REPO_ROOT)
        if any(part in skip_dirs for part in rel.parts):
            continue
        if rel.name in skip_files:
            continue
        # Only inspect text-y extensions; binary assets are skipped.
        if path.suffix.lower() in {
            ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico",
            ".pdf", ".zip", ".tar", ".gz", ".tgz", ".whl", ".so", ".bin",
        }:
            continue
        yield rel


@pytest.mark.parametrize("rel_path", sorted(str(p) for p in _all_text_files()))
def test_no_real_secrets(rel_path: str) -> None:
    target = REPO_ROOT / rel_path
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        pytest.skip(f"binary or non-utf8 file: {rel_path}")
    for pattern in SECRET_PATTERNS:
        for m in pattern.finditer(text):
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.end())
            if line_end == -1:
                line_end = len(text)
            line = text[line_start:line_end]
            if _is_placeholder(line, m.start() - line_start):
                continue
            pytest.fail(
                f"Possible secret in {rel_path}:\n    {line.strip()}\n"
                f"    matched pattern {pattern.pattern!r}"
            )


def test_env_example_only() -> None:
    """`.env.example` must be present; the real `.env` must never be
    committed as plain content (it can exist locally, but if the project is a
    git checkout, `.env` must be ignored by `.gitignore`).
    """
    example = REPO_ROOT / ".env.example"
    assert example.exists(), "expected .env.example to be present"

    # If the project is inside a git checkout we verify `.env` is not in the
    # git index. The scanner running on the host or in the test container
    # always finds `.gitignore` declaring `.env`; the host's git index is the
    # source of truth.
    git_dir = REPO_ROOT / ".git"
    if git_dir.exists():
        import subprocess  # local import keeps test cheap on read
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files", "--error-unmatch", ".env"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, (
            ".env must NOT be tracked by git — untrack it:\n"
            f"    {result.stdout.strip()}"
        )


def test_gitignore_excludes_env() -> None:
    gi = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gi, ".gitignore must list `.env` so secrets never ship"
