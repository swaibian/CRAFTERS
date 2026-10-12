"""SWE4 unit tests for gateway/logger.py (SWE3-A-01).

Positive: safe fields pass through; nested redaction scrubs secrets;
operational/audit/metrics loggers are distinct.
Negative (forbidden-field cases): tokens, secrets, document content, image
data, transcripts, raw bodies/params never survive safe_event/redact_value;
bytes are scrubbed; overlong strings truncated; unknown fields dropped.
"""

from __future__ import annotations

import logging

from gateway.logger import (
    get_audit_logger,
    get_logger,
    get_metrics_logger,
    redact_value,
    safe_event,
)

SECRET = "sk-live-abcdef123456"


def test_safe_event_keeps_allowlisted_fields() -> None:
    event = safe_event(
        event="tool_ingress", tool="craft_status", user_id="alice", ok=True
    )
    assert event == {
        "event": "tool_ingress",
        "tool": "craft_status",
        "user_id": "alice",
        "ok": True,
    }


def test_safe_event_drops_unknown_fields() -> None:
    event = safe_event(event="x", tool="craft_status", whatever="drop me")
    assert "whatever" not in event


def test_redact_value_scrubs_secret_keys() -> None:
    payload = {
        "user_id": "alice",
        "token": SECRET,
        "authorization": "Bearer abc",
        "api_key": "k",
        "nested": {"password": "p", "image": "iVBOR...", "ok": 1},
    }
    scrubbed = redact_value(payload)
    text = str(scrubbed)
    assert SECRET not in text
    assert scrubbed["user_id"] == "alice"
    assert scrubbed["token"] == "[redacted]"
    assert scrubbed["nested"] == {
        "password": "[redacted]",
        "image": "[redacted]",
        "ok": 1,
    }


def test_redact_value_scrubs_content_and_transcripts() -> None:
    payload = {
        "document": "full file text",
        "transcript": "private chat",
        "prompt": "system prompt",
        "body": {"raw": 1},
        "params": {"command": "run"},
        "args": [1, 2],
        "render": "pixels",
        "content": [{"type": "image"}],
    }
    scrubbed = redact_value(payload)
    for key in payload:
        assert scrubbed[key] == "[redacted]", key


def test_redact_value_scrubs_bytes_and_truncates_long_strings() -> None:
    assert redact_value(b"\x89PNG...") == "[redacted]"
    assert redact_value(bytearray(b"img")) == "[redacted]"
    long_text = "x" * 600
    scrubbed = redact_value({"note": long_text, "event": "e"})
    assert len(scrubbed["note"]) < len(long_text)
    assert "truncated" in scrubbed["note"]


def test_redact_value_does_not_mutate_input() -> None:
    payload = {"token": SECRET, "items": [{"secret": "s"}]}
    redact_value(payload)
    assert payload == {"token": SECRET, "items": [{"secret": "s"}]}


def test_safe_event_never_emits_secrets() -> None:
    event = safe_event(
        event="auth_decision",
        user_id="alice",
        tool="t",
        ok=False,
        token=SECRET,
        password="p",
    )
    assert SECRET not in str(event)
    assert "token" not in event and "password" not in event


def test_logger_names_separate_sinks() -> None:
    assert get_logger().name == "gateway"
    assert get_audit_logger().name == "gateway.audit"
    assert get_metrics_logger().name == "gateway.metrics"
    assert logging.getLogger("gateway.audit").parent is logging.getLogger("gateway")
