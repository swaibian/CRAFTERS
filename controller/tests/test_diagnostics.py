"""SWE4 tests: diagnostics ring buffer + probes (no live ports needed).

Positive: record/recent ordering + newest-first, 200-entry bound, gateway
TCP probe shape, controller self check, scaico/litellm not-configured
shapes, scaico_info success mapping (X-API-Key header, base default/env
override), GET /api/diagnostics live shape via TestClient.
Negative: unparsable gateway endpoint, scaico transport failure, litellm
ping failure, key absence in every response (canary secrets).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from controller import diagnostics as diag
from controller.service import ServiceState, create_app
from controller.settings import SettingsStore


@pytest.fixture()
def client(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setenv("CRAFTER_SETTINGS_FILE", str(settings_path))
    state = ServiceState(
        settings=SettingsStore(path=settings_path),
        work_root=tmp_path / "work",
    )
    return TestClient(create_app(state))


def test_ring_buffer_newest_first_and_bound():
    log = diag.DiagnosticsLog(maxlen=5)
    for i in range(7):
        log.record("svc", True, detail=f"d{i}")
    items = log.recent(10)
    assert len(items) == 5
    assert [e["detail"] for e in items] == ["d6", "d5", "d4", "d3", "d2"]
    assert all(set(e) <= {"at", "service", "ok", "latency_ms", "detail"} for e in items)
    assert log.recent(2)[0]["detail"] == "d6"
    # Records are copies (mutating the result must not corrupt the buffer).
    items[0]["service"] = "mutated"
    assert log.recent(1)[0]["service"] == "svc"


def test_singleton_record_recent_helpers():
    diag.DIAGNOSTICS._entries.clear()
    diag.record("gateway", True, latency_ms=3, detail="ok")
    assert diag.recent(1)[0]["service"] == "gateway"
    diag.DIAGNOSTICS._entries.clear()


def test_probe_controller_self():
    assert diag.probe_controller() == {"ok": True}


def test_probe_gateway_unparsable():
    assert diag.probe_gateway("not-a-url") == {
        "ok": False,
        "detail": "unparsable endpoint",
    }
    assert diag.probe_gateway("") == {"ok": False, "detail": "unparsable endpoint"}


def test_probe_gateway_tcp_ok_and_fail(monkeypatch):
    import socket

    class _Sock:
        def close(self):
            pass

    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: _Sock())
    ok = diag.probe_gateway("http://127.0.0.1:8787")
    assert ok["ok"] is True and "latency_ms" in ok

    def _fail(*a, **k):
        raise OSError("refused")

    monkeypatch.setattr(socket, "create_connection", _fail)
    bad = diag.probe_gateway("http://127.0.0.1:9")
    assert bad == {"ok": False, "detail": "tcp connect failed"}


def test_probe_scaico_not_configured():
    assert diag.probe_scaico("") == {"ok": False, "configured": False}


def test_scaico_info_success_and_base(monkeypatch):
    import httpx

    seen: dict = {}

    def fake_get(url, headers=None, timeout=None):
        seen["url"] = url
        seen["headers"] = dict(headers)
        return httpx.Response(200, json={"name": "scaico"})

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.delenv("SCAICO_PUBLIC_API_BASE_URL", raising=False)
    result = diag.scaico_info("scaico-CANARY-Info-1234")
    assert result["ok"] is True and "latency_ms" in result
    assert seen["url"] == "http://127.0.0.1:9000/public_api/api/info"
    assert seen["headers"] == {
        "Accept": "application/json",
        "X-API-Key": "scaico-CANARY-Info-1234",
    }
    assert "scaico-CANARY-Info-1234" not in str(result)

    monkeypatch.setenv("SCAICO_PUBLIC_API_BASE_URL", "http://example.test:9000/base/")
    diag.scaico_info("k")
    assert seen["url"] == "http://example.test:9000/base/api/info"


def test_scaico_info_transport_and_status(monkeypatch):
    import httpx

    def _down(url, headers=None, timeout=None):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "get", _down)
    assert diag.scaico_info("scaico-CANARY-Down-1") == {
        "ok": False,
        "error": "scaico unreachable",
    }

    def _403(url, headers=None, timeout=None):
        return httpx.Response(403, json={"detail": "bad key"})

    monkeypatch.setattr(httpx, "get", _403)
    bad = diag.scaico_info("scaico-CANARY-Bad-2")
    assert bad["ok"] is False and bad["status"] == 403
    assert "scaico-CANARY-Bad-2" not in str(bad)


def test_probe_litellm_not_configured():
    assert diag.probe_litellm(None) == {"ok": False, "configured": False}


def test_probe_litellm_ping_and_failure(monkeypatch):
    import httpx

    from controller.llm import LlmClient

    def fake_ping(self):
        assert self._timeout == 5.0
        return {"reachable": True, "models": ["m"]}

    monkeypatch.setattr(LlmClient, "ping", fake_ping)

    class _Profile:
        api_base = "http://127.0.0.1:9/v1"
        api_key = "sk-CANARY-LiteLLM-1"
        default_model = "m"

    ok = diag.probe_litellm(_Profile())
    assert ok["ok"] is True and "latency_ms" in ok
    assert "sk-CANARY-LiteLLM-1" not in str(ok)
    monkeypatch.undo()  # drop the ping fake; exercise the real failure path

    def _boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "get", _boom)
    bad = diag.probe_litellm(_Profile())
    assert bad["ok"] is False and "error" in bad
    assert "sk-CANARY-LiteLLM-1" not in str(bad)


def test_probe_all_keys_and_bounded(client, monkeypatch):
    import socket

    class _Sock:
        def close(self):
            pass

    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: _Sock())
    checks = diag.probe_all(client.app.state.controller.settings)
    assert set(checks) == {"gateway", "controller", "scaico", "litellm"}


def test_diagnostics_route_no_key_echo(client, monkeypatch):
    import socket

    import httpx

    from controller import diagnostics as diag_mod

    diag_mod.DIAGNOSTICS._entries.clear()

    class _Sock:
        def close(self):
            pass

    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: _Sock())
    # Stored key → scaico probe would do real HTTP; fake it (no live ports).
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *a, **k: httpx.Response(200, json={"name": "scaico"}),
    )
    client.put("/api/settings/scaico-key", json={"api_key": "scaico-CANARY-Route-5"})
    resp = client.get("/api/diagnostics")
    assert resp.status_code == 200
    assert "scaico-CANARY-Route-5" not in resp.text
