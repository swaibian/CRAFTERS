"""Controller logger: stdlib logging with secret/content redaction.

Mirrors the gateway/logger.py contract (allow-listed safe fields, recursive
scrub) so controller logs carry the same guarantee: API keys, tokens,
document content, image bytes, and transcripts never reach a log record.
Enforced by controller/tests/test_logging_redaction.py.

SW-REQ: SW-REQ-STREAM (logging allocation: never log keys/prompts/content).
"""

from __future__ import annotations

import logging
from typing import Any

OPERATIONAL_LOGGER = "crafter.controller"
AUDIT_LOGGER = "crafter.controller.audit"

SAFE_FIELDS = frozenset(
    {
        "event",
        "tool",
        "app",
        "adapter",
        "op",
        "doc_id",
        "session_id",
        "user_id",
        "key_id",
        "profile_id",
        "run_id",
        "iteration",
        "ok",
        "error",
        "error_code",
        "count",
        "revision",
        "content_hash",
        "duration_ms",
        "route",
        "status",
        "service",
        "model",
        "team",
        "latency_ms",
        "call_id",
        "outcome",
    }
)

FORBIDDEN_KEY_PARTS = (
    "token",
    "bearer",
    "authorization",
    "secret",
    "password",
    "api_key",
    "apikey",
    "credential",
    "session_key",
    "private_key",
    "image",
    "picture",
    "content",
    "document",
    "transcript",
    "prompt",
    "body",
    "payload",
    "file_bytes",
    "render",
    "args",
    "params",
    "arguments",
    "message",
    "text",
    "claim",
    "note",
    "evidence",
)

REDACTED = "[redacted]"
TRUNCATE_AT = 500


def get_logger(name: str = OPERATIONAL_LOGGER) -> logging.Logger:
    """Return the controller operational logger.

    :param name: Logger name; defaults to ``crafter.controller``.
    :returns: A stdlib logger (callers configure handlers; never added here).
    """
    return logging.getLogger(name)


def configure_operational_logging() -> None:
    """Enable redacted controller events in the local server's stderr log."""
    logger = get_logger()
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = True


def get_audit_logger() -> logging.Logger:
    """Return the controller audit logger (settings/auth decisions).

    :returns: Logger named ``crafter.controller.audit``.
    """
    return logging.getLogger(AUDIT_LOGGER)


def _is_forbidden_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in FORBIDDEN_KEY_PARTS)


def redact_value(obj: Any) -> Any:
    """Recursively scrub secrets and content payloads from a value.

    Dict keys matching :data:`FORBIDDEN_KEY_PARTS` become ``[redacted]``;
    ``bytes``/``bytearray`` become ``[redacted]``; strings longer than 500
    chars are truncated. The input is never mutated.

    :param obj: Any JSON-ish value.
    :returns: Scrubbed copy safe to log.
    """
    if isinstance(obj, dict):
        return {
            key: (REDACTED if _is_forbidden_key(str(key)) else redact_value(value))
            for key, value in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        scrubbed = [redact_value(item) for item in obj]
        return type(obj)(scrubbed) if isinstance(obj, tuple) else scrubbed
    if isinstance(obj, (bytes, bytearray)):
        return REDACTED
    if isinstance(obj, str) and len(obj) > TRUNCATE_AT:
        return obj[:TRUNCATE_AT] + "…[truncated]"
    return obj


def safe_event(**fields: Any) -> dict[str, Any]:
    """Build a log-safe event dict from allow-listed fields only.

    Unknown fields are dropped; kept fields pass through
    :func:`redact_value` as defense in depth.

    :param fields: Candidate event fields.
    :returns: Dict containing only :data:`SAFE_FIELDS` keys, scrubbed.
    """
    return {
        key: redact_value(value) for key, value in fields.items() if key in SAFE_FIELDS
    }
