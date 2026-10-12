"""Project logger for the Crafter gateway.

Stdlib ``logging`` only — no private logging setup. Three separate sinks by
logger name so operators can route them independently:

- ``gateway`` — operational logs (tool ingress/egress, CLI spawn/proxy).
- ``gateway.audit`` — security-audit records (auth allow/deny decisions).
- ``gateway.metrics`` — counters/timings, never mixed into audit records.

Every log call site must pass its fields through :func:`safe_event` (allow-list
of safe field names) or :func:`redact_value` (recursive scrub). Tokens,
secrets, document content, image data, transcripts and raw bodies must never
reach a log record — enforced by ``gateway/tests/test_logger.py``.

SW-REQ: SW-REQ-GW-CORE (logging & observability allocation, TC-A-00).
"""

from __future__ import annotations

import logging
from typing import Any

OPERATIONAL_LOGGER = "gateway"
AUDIT_LOGGER = "gateway.audit"
METRICS_LOGGER = "gateway.metrics"

# Fields that are always safe to log. Anything else is dropped by safe_event.
SAFE_FIELDS = frozenset(
    {
        "event",
        "tool",
        "app",
        "method",
        "command",
        "user_id",
        "key_id",
        "session_id",
        "duration_ms",
        "ok",
        "error",
        "error_code",
        "revision",
        "transport",
        "host",
        "port",
        "path",
        "count",
        "available",
        "mode",
    }
)

# Substrings of dict keys whose values must be scrubbed wherever they appear.
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
)

REDACTED = "[redacted]"
TRUNCATE_AT = 500


def get_logger(name: str = OPERATIONAL_LOGGER) -> logging.Logger:
    """Return the operational logger (runtime-boundary events).

    :param name: Logger name; defaults to ``gateway``.
    :returns: A stdlib logger. Callers configure handlers; this module never
        adds handlers or formatters itself.
    """
    return logging.getLogger(name)


def get_audit_logger() -> logging.Logger:
    """Return the security-audit logger (auth allow/deny decisions).

    :returns: Logger named ``gateway.audit`` — route separately from
        operational logs.
    """
    return logging.getLogger(AUDIT_LOGGER)


def get_metrics_logger() -> logging.Logger:
    """Return the metrics logger (counters/timings, no audit content).

    :returns: Logger named ``gateway.metrics``.
    """
    return logging.getLogger(METRICS_LOGGER)


def _is_forbidden_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in FORBIDDEN_KEY_PARTS)


def redact_value(obj: Any) -> Any:
    """Recursively scrub secrets and content payloads from a value.

    Dict keys matching :data:`FORBIDDEN_KEY_PARTS` are replaced with
    ``[redacted]``; ``bytes``/``bytearray`` become ``[redacted]``; strings
    longer than 500 chars are truncated (they may carry document content).
    The input is never mutated — a scrubbed copy is returned.

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

    Unknown fields are dropped (never logged); kept fields are still passed
    through :func:`redact_value` as defense in depth.

    :param fields: Candidate event fields.
    :returns: Dict containing only :data:`SAFE_FIELDS` keys, scrubbed.
    """
    return {
        key: redact_value(value) for key, value in fields.items() if key in SAFE_FIELDS
    }


def log_tool_ingress(
    logger: logging.Logger,
    *,
    tool: str,
    user_id: str,
    session_id: str,
    key_id: str = "",
) -> None:
    """Log a tool-call ingress boundary event with safe fields only.

    :param logger: Operational logger from :func:`get_logger`.
    :param tool: Tool name being invoked.
    :param user_id: Authenticated user id (never a token).
    :param session_id: Session id for context propagation.
    :param key_id: Non-secret token identifier for correlation.
    """
    logger.info(
        "tool ingress: %s",
        safe_event(
            event="tool_ingress",
            tool=tool,
            user_id=user_id,
            session_id=session_id,
            key_id=key_id,
        ),
    )


def log_auth_decision(
    *,
    user_id: str,
    tool: str,
    ok: bool,
    key_id: str = "",
    error_code: str = "",
) -> None:
    """Log an auth allow/deny decision to the audit logger.

    :param user_id: User id the decision applies to (never a token).
    :param tool: Tool name requested.
    :param ok: Whether access was granted.
    :param key_id: Non-secret token identifier for correlation.
    :param error_code: Machine-readable denial reason (no secrets).
    """
    get_audit_logger().info(
        "auth %s",
        safe_event(
            event="auth_decision",
            user_id=user_id,
            tool=tool,
            ok=ok,
            key_id=key_id,
            error_code=error_code,
        ),
    )
