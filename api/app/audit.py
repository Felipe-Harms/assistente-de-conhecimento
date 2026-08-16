"""Structured audit logger (REQ-007 foundation).

Emits JSON lines with request_id, user/principal, path, status, latency_ms.
Includes a conservative redaction pass: bearer tokens, JWT-like strings and
anything matching the literal patterns in REDACT_PATTERNS are masked before
logging. The redaction happens on BOTH keys (path/method/...) and the free-form
`message` body so accidental leakage from middleware is reduced.

The logger is intentionally fire-and-forget — it never raises into the caller.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

# Conservative — keep tunable but never log raw credentials.
REDACT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)([A-Za-z0-9._\-]+)"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{8,}\b"),
)
REDACT_REPLACEMENT = "[REDACTED]"


def scrub(value: Any) -> Any:
    """Return a redacted copy of *value* if it is a string; otherwise unchanged."""
    if not isinstance(value, str):
        return value
    out = value
    for pattern in REDACT_PATTERNS:
        out = pattern.sub(REDACT_REPLACEMENT, out)
    return out


def scrub_mapping(mapping: Mapping[str, Any] | None) -> dict[str, Any]:
    """Apply scrub() to every value; redact sensitive-looking keys wholesale."""
    if not mapping:
        return {}
    sensitive_keys = {"authorization", "x-api-key", "api-key", "api_key", "cookie"}
    result: dict[str, Any] = {}
    for key, val in mapping.items():
        if key.lower() in sensitive_keys:
            result[key] = REDACT_REPLACEMENT
        else:
            result[key] = scrub(val)
    return result


@dataclass
class AuditEvent:
    """One audit event. Emitted as a single JSON line by `emit()`."""

    timestamp_ms: int
    request_id: str
    principal: str | None
    method: str
    path: str
    status: int
    latency_ms: float
    message: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        payload: dict[str, Any] = {
            "ts": self.timestamp_ms,
            "rid": self.request_id,
            "principal": self.principal,
            "method": self.method,
            "path": self.path,
            "status": self.status,
            "latency_ms": round(self.latency_ms, 3),
        }
        if self.message:
            payload["message"] = scrub(self.message)
        if self.extra:
            payload["extra"] = scrub_mapping(self.extra)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class AuditLogger:
    """In-memory structured logger. Output goes to STDOUT via Python `print`.

    The base implementation never raises; collectors are added in later tasks.
    """

    def emit(self, event: AuditEvent) -> None:
        try:
            print(event.to_json(), flush=True)
        except Exception:  # pragma: no cover — fire-and-forget
            pass


def make_audit_logger() -> AuditLogger:
    return AuditLogger()


def now_ms() -> int:
    return int(time.time() * 1000)


def timed_ms(start_ms: int) -> float:
    return (now_ms() - start_ms) * 1.0


__all__ = [
    "AuditEvent",
    "AuditLogger",
    "make_audit_logger",
    "scrub",
    "scrub_mapping",
    "now_ms",
    "timed_ms",
]
