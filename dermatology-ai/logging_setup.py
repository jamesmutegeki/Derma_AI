"""Structured logging with secret redaction.

A clinical service must be able to say *what* happened without leaking *who* or
*with which credential*.  Two rules are enforced here:

* any ``Bearer <token>`` substring is replaced before the record is emitted;
* anything that looks like a bcrypt hash is replaced.

Patient fields are simply never passed to the logger -- that rule is asserted by
``tests/test_s1_3_phi_handling.py`` and ``tests/test_s2_1_operability.py``.
"""

from __future__ import annotations

import logging
import re

REDACTED = "[redacted]"

_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"(\$2[aby]\$\d{2}\$)[A-Za-z0-9./]+"),
    re.compile(r"(authorization[\"']?\s*[:=]\s*)[^\s,}\"']+", re.IGNORECASE),
]


def redact(text: str) -> str:
    """Return ``text`` with credentials masked."""
    if not text:
        return text
    for pattern in _PATTERNS:
        text = pattern.sub(lambda match: match.group(1) + REDACTED, text)
    return text


class RedactionFilter(logging.Filter):
    """Mask credentials in every record that passes through."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - logging API
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            return True
        cleaned = redact(message)
        if cleaned != message:
            record.msg = cleaned
            record.args = ()
        return True


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root logging once, idempotently, with redaction attached."""
    root = logging.getLogger()
    if not any(isinstance(f, RedactionFilter) for f in root.filters):
        root.addFilter(RedactionFilter())
    if root.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    ))
    handler.addFilter(RedactionFilter())
    root.addHandler(handler)
    root.setLevel(level)
