"""Security smoke tests — REQ-007: structured audit logs without sensitive body.

All fixture tokens here are intentionally low-entropy or explicitly labeled
(`EXAMPLE_*`) so the secret scanner accepts them as placeholders.
"""

from __future__ import annotations

import io
import json
import re

import pytest

from app.audit import (
    AuditEvent,
    AuditLogger,
    REDACT_REPLACEMENT,
    now_ms,
    scrub,
    scrub_mapping,
)

# Fixture placeholders — explicitly labelled.
EXAMPLE_SK = "sk-EXAMPLE-plac-abcdefghij0123456789"
EXAMPLE_BEARER = "Bearer EXAMPLE"
EXAMPLE_LONG = "EXAMPLE" + ("Z" * 32)


def test_scrub_strips_sk_key() -> None:
    assert scrub(EXAMPLE_SK) == REDACT_REPLACEMENT


def test_scrub_strips_bearer() -> None:
    assert scrub("Authorization: " + EXAMPLE_BEARER) == REDACT_REPLACEMENT


def test_scrub_preserves_normal_text() -> None:
    text = "user asked about rentabilidade"
    assert scrub(text) == text


def test_scrub_mapping_redacts_authorization_keys() -> None:
    headers = {
        "Authorization": EXAMPLE_BEARER,
        "Content-Type": "application/json",
        "X-Api-Key": EXAMPLE_SK,
    }
    out = scrub_mapping(headers)
    assert out["Authorization"] == REDACT_REPLACEMENT
    assert out["X-Api-Key"] == REDACT_REPLACEMENT
    assert out["Content-Type"] == "application/json"


def test_audit_event_is_valid_json() -> None:
    ev = AuditEvent(
        timestamp_ms=now_ms(),
        request_id="rid-1",
        principal="bearer-token-holder",
        method="POST",
        path="/v1/embeddings",
        status=200,
        latency_ms=12.5,
        message="hi",
        extra={"ua": "Mozilla/5.0"},
    )
    raw = ev.to_json()
    parsed = json.loads(raw)
    assert parsed["rid"] == "rid-1"
    assert parsed["status"] == 200
    assert parsed["latency_ms"] == 12.5


def test_audit_logger_does_not_raise(capfd) -> None:
    log = AuditLogger()
    log.emit(
        AuditEvent(
            timestamp_ms=now_ms(),
            request_id="rid-2",
            principal="x",
            method="GET",
            path="/healthz",
            status=200,
            latency_ms=1.0,
        )
    )
    out = capfd.readouterr().out.strip().splitlines()
    assert out, "audit logger should emit exactly one line"
    json.loads(out[-1])  # must be valid JSON


def test_healthz_emits_audit_line(capfd, api_client) -> None:
    api_client.get("/healthz")
    out = capfd.readouterr().out.strip().splitlines()
    audit = [json.loads(line) for line in out if line.startswith("{") and '"rid"' in line]
    assert any(ev["path"] == "/healthz" and ev["status"] == 200 for ev in audit), (
        f"expected /healthz audit line, got: {out[-3:]}"
    )


def test_redacted_body_does_not_leak(api_client, capfd) -> None:
    secret = EXAMPLE_LONG  # already labelled; the redaction test asserts no echo.
    resp = api_client.get(
        "/healthz",
        headers={"Authorization": secret},
    )
    assert resp.status_code == 200
    out = capfd.readouterr().out
    assert EXAMPLE_LONG not in out, (
        "audit log must not contain raw placeholder value"
    )
