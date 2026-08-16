"""Integration tests share fixtures with the parent suite.

The shared fixtures (`app_client`, `fresh_workspace`) and the
`CORPUS_DIR` constant live in `tests/conftest.py` so both `integration`
and `acceptance` tests can use them. This module-level shim keeps
backward compatibility for tests that imported the old `conftest`
symbols directly.
"""

from __future__ import annotations

import os
import socket
import time
from pathlib import Path

import pytest

# --- environment preflight ---------------------------------------------------
_DB_HOST = os.environ.get("POSTGRES_HOST", "db")
_DB_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))


def _wait_for_db(timeout_s: float = 30.0) -> None:
    deadline = time.time() + timeout_s
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with socket.create_connection((_DB_HOST, _DB_PORT), timeout=2):
                return
        except Exception as exc:
            last_err = exc
            time.sleep(0.5)
    raise RuntimeError(f"db not reachable: {last_err}")


@pytest.fixture(scope="session", autouse=True)
def _db_preflight() -> None:
    _wait_for_db()


# Re-export the shared fixtures so tests that imported them from this
# conftest keep working.
from tests.conftest import (  # noqa: E402, F401
    REPO_ROOT,
    CORPUS_DIR,
    app_client,
    fresh_workspace,
)
