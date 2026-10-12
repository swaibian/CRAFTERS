"""SWE4 tests: controller logger redaction (keys/content/image-bytes never logged)."""

from __future__ import annotations

from controller.logger import redact_value, safe_event


def test_redact_value_scrubs_forbidden_keys():
    payload = {
        "api_key": "sk-secret-123",
        "message": "hello user content",
        "count": 3,
        "nested": {"image_bytes": b"\x89PNG", "ok": True},
    }
    scrubbed = redact_value(payload)
    assert scrubbed["api_key"] == "[redacted]"
    assert scrubbed["message"] == "[redacted]"
    assert scrubbed["count"] == 3
    assert scrubbed["nested"]["image_bytes"] == "[redacted]"
    assert scrubbed["nested"]["ok"] is True
    # Input never mutated.
    assert payload["api_key"] == "sk-secret-123"


def test_redact_value_bytes_and_long_strings():
    assert redact_value(b"\x00\x01") == "[redacted]"
    long_text = "x" * 600
    scrubbed = redact_value(long_text)
    assert len(scrubbed) < 600 and "truncated" in scrubbed


def test_safe_event_drops_unknown_fields():
    event = safe_event(
        event="chat_stream", session_id="s1", message="user said secrets", ok=True
    )
    assert event["event"] == "chat_stream"
    assert event["session_id"] == "s1"
    assert "message" not in event
    assert event["ok"] is True


def test_safe_event_allows_new_operational_fields():
    """New SAFE_FIELDS (service/model/team/latency_ms) flow; keys still dropped."""
    event = safe_event(
        event="diagnostic_probe",
        service="scaico",
        model="m-a",
        team="craft_studio",
        latency_ms=12,
        api_key="sk-CANARY-Redact-1",
        ok=True,
    )
    assert event["service"] == "scaico"
    assert event["model"] == "m-a"
    assert event["team"] == "craft_studio"
    assert event["latency_ms"] == 12
    assert "api_key" not in event


def test_redact_value_scrubs_model_and_team_content():
    """Model/team values pass (routing metadata); content-ish keys scrubbed."""
    scrubbed = redact_value(
        {"model": "m-a", "team": "craft_studio", "detail": "tcp connect ok"}
    )
    assert scrubbed == {
        "model": "m-a",
        "team": "craft_studio",
        "detail": "tcp connect ok",
    }
    assert redact_value({"api_key": "sk-CANARY-Redact-2"}) == {"api_key": "[redacted]"}
