"""PHI-safe logging boundary (HIPAA zero-persistence enforcement).

The pipeline writes progress via print() and logger.*, and start.sh redirects
stdout+stderr to a persistent logs/backend.log. Without this module, any patient
identifier or clinical string emitted to the console persists on disk forever —
violating the zero-persistence architecture.

`install_phi_safe_logging()` installs a redaction boundary at the console:
  * sys.stdout / sys.stderr are wrapped so EVERY write (print() AND the logging
    StreamHandler) is scrubbed of structured identifiers before it can be written
    to the log file — a backstop that holds even for code added later.
  * a logging.Filter is attached to the root logger as a second layer.

Regex can reliably remove STRUCTURED identifiers (SSN, MRN, phone, DOB, email).
It CANNOT reliably remove free-text names / clinical prose — those must not be
emitted at the source (callers log counts/lengths/IDs, never patient content).
This module is the safety net; the source discipline is the primary control.
"""
from __future__ import annotations

import logging
import re
import sys

_PATTERNS = [
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),                      # SSN
    (re.compile(r"(?i)\bSSN\b\s*[:=#]?\s*\d{3}[- ]?\d{2}[- ]?\d{4}"), "SSN [REDACTED]"),
    (re.compile(r"\(?\b\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"), "[PHONE]"),    # phone
    (re.compile(r"(?i)\b(?:DOB|date\s+of\s+birth)\b\s*[:=]?\s*"
                r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"), "DOB [REDACTED]"),
    (re.compile(r"(?i)\bMRN\b\s*[:=#]?\s*\d{3,}"), "MRN [REDACTED]"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[EMAIL]"),             # email
]


def redact(text):
    """Scrub structured PHI identifiers from a string. Non-str passes through."""
    if not isinstance(text, str) or not text:
        return text
    try:
        for pat, repl in _PATTERNS:
            text = pat.sub(repl, text)
    except Exception:  # never let redaction break logging
        pass
    return text


class _RedactingStream:
    """Thin wrapper that redacts on write; delegates everything else."""

    def __init__(self, stream):
        self._stream = stream

    def write(self, data):
        try:
            return self._stream.write(redact(data))
        except Exception:
            return self._stream.write(data)

    def writelines(self, lines):
        for line in lines:
            self.write(line)

    def flush(self):
        try:
            self._stream.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._stream, name)


class PHIRedactionFilter(logging.Filter):
    """Second layer: redact the message + args of every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = redact(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {k: redact(v) for k, v in record.args.items()}
                else:
                    record.args = tuple(redact(a) for a in record.args)
        except Exception:
            pass
        return True


_installed = False


def install_phi_safe_logging() -> None:
    """Idempotent. Call BEFORE logging.basicConfig so the StreamHandler binds the
    wrapped stream."""
    global _installed
    if _installed:
        return
    if not isinstance(sys.stdout, _RedactingStream):
        sys.stdout = _RedactingStream(sys.stdout)
    if not isinstance(sys.stderr, _RedactingStream):
        sys.stderr = _RedactingStream(sys.stderr)
    root = logging.getLogger()
    root.addFilter(PHIRedactionFilter())
    for h in root.handlers:
        h.addFilter(PHIRedactionFilter())
    _installed = True
