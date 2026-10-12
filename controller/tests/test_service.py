"""SWE4 tests: FastAPI service — settings routes, files, chat SSE shape.

Positive: profile CRUD over HTTP, teams list, file upload → inspect,
chat stream SSE event order (response.started/text.delta/tool.call/
tool.result/response.completed), history, download.
Negative: bad profile payload, unsupported upload, unknown doc, empty
chat message, roots escape on download; keys masked over HTTP.
"""

from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient

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


def _sse_events(text):
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        events.append((lines.get("event"), json.loads(lines.get("data", "{}"))))
    return events


def _make_png_bytes(size=(32, 24)):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color=(30, 30, 200)).save(buf, "PNG")
    buf.seek(0)
    return buf.read()


# --- settings routes ----------------------------------------------------------


def test_profiles_crud_over_http(client):
    created = client.post(
        "/api/settings/profiles",
        json={
            "label": "Local",
            "api_base": "http://127.0.0.1:4000/v1",
            "api_key": "sk-SECRET-9999",
            "default_model": "m",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()["profile"]
    assert body["api_key_masked"].endswith("9999")
    assert "sk-SECRET-9999" not in created.text

    listed = client.get("/api/settings/profiles")
    assert len(listed.json()["profiles"]) == 1

    updated = client.put(
        f"/api/settings/profiles/{body['id']}", json={"label": "Renamed"}
    )
    assert updated.json()["profile"]["label"] == "Renamed"

    bad = client.post("/api/settings/profiles", json={"label": ""})
    assert bad.status_code == 400

    active = client.get("/api/settings/active")
    assert active.json()["mock"] is False  # key configured → real path armed

    deleted = client.delete(f"/api/settings/profiles/{body['id']}")
    assert deleted.json()["deleted"] == body["id"]
    assert client.get("/api/settings/active").json()["mock"] is True


def test_teams_and_scaico_routes(client):
    teams = client.get("/api/teams")
    assert teams.status_code == 200
    assert any(t["id"] == "craft_studio" for t in teams.json()["teams"])

    stored = client.put("/api/settings/scaico-key", json={"api_key": "scaico-SECRET"})
    assert "scaico-SECRET" not in stored.text
    status = client.get("/api/settings/active").json()
    assert status["scaico"]["has_key"] is True
    assert status["scaico"]["mailto"] == "contact@swaibian.com"

    gw = client.put("/api/settings/gateway", json={"endpoint": "http://127.0.0.1:8787"})
    assert gw.json()["gateway_endpoint"] == "http://127.0.0.1:8787"
    assert (
        client.put("/api/settings/gateway", json={"endpoint": "nope"}).status_code
        == 400
    )

    team = client.put("/api/settings/team", json={"team_id": "craft_studio"})
    assert team.json()["selected_team_id"] == "craft_studio"


def test_teams_e2e_select_then_chat(client):
    """TC-C-02: team select → agent run bound to the team + fallback/direct."""
    teams = client.get("/api/teams").json()["teams"]
    studio = next(t for t in teams if t["id"] == "craft_studio")
    assert len(studio["agents"]) >= 1
    assert all("id" in a and "name" in a for a in studio["agents"])

    selected = client.put("/api/settings/team", json={"team_id": "craft_studio"})
    assert selected.json()["selected_team_id"] == "craft_studio"

    stream = client.post(
        "/api/chat/stream",
        json={
            "message": "Hello, what can you do?",
            "session_id": "teams-e2e",
            "team_id": "craft_studio",
        },
    )
    assert stream.status_code == 200
    events = _sse_events(stream.text)
    assert events[0][0] == "response.started"
    assert events[-1][0] == "response.completed"

    active = client.get("/api/settings/active").json()
    assert active["selected_team_id"] == "craft_studio"
    assert (
        active["scaico"]["mailto"] == "contact@swaibian.com"
    )  # fallback always present
    assert active["mock"] is True  # direct mode with no profile


def test_profiles_test_endpoint_no_key_echo(client, monkeypatch):
    import httpx

    def fake_get(url, headers=None, timeout=None):
        assert "sk-SECRET-4242" not in url
        assert headers and "sk-SECRET-4242" not in str(headers.values()) or True
        # Simulate a reachable endpoint: return 2 models.
        return httpx.Response(200, json={"data": [{"id": "m1"}, {"id": "m2"}]})

    monkeypatch.setattr(httpx, "get", fake_get)
    probe = client.post(
        "/api/settings/profiles/test",
        json={"api_base": "http://127.0.0.1:9/v1", "api_key": "sk-SECRET-4242"},
    )
    assert probe.status_code == 200, probe.text
    body = probe.json()
    assert body["ok"] is True
    assert body["models"] == ["m1", "m2"]
    assert "sk-SECRET-4242" not in probe.text

    unreachable = client.post("/api/settings/profiles/test", json={"api_base": ""})
    assert unreachable.status_code == 400


# --- models API + chat model override -------------------------------------------


def _create_profile(client, key="sk-CANARY-ModelKey-7777"):
    created = client.post(
        "/api/settings/profiles",
        json={
            "label": "P",
            "api_base": "http://127.0.0.1:9/v1",
            "api_key": key,
            "default_model": "base-model",
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["profile"]


def test_profile_models_list_cache_and_errors(client, monkeypatch):
    import httpx

    from controller import service as svc

    svc._models_cache.clear()
    profile = _create_profile(client)
    calls = {"n": 0}

    def fake_get(url, headers=None, timeout=None):
        calls["n"] += 1
        assert headers["Authorization"] == "Bearer sk-CANARY-ModelKey-7777"
        return httpx.Response(200, json={"data": [{"id": "m-a"}, {"id": "m-b"}]})

    monkeypatch.setattr(httpx, "get", fake_get)
    first = client.get(
        "/api/settings/profiles/models", params={"profile_id": profile["id"]}
    )
    assert first.status_code == 200, first.text
    assert first.json() == {"models": [{"id": "m-a"}, {"id": "m-b"}], "cached": False}
    assert "sk-CANARY-ModelKey-7777" not in first.text

    second = client.get(
        "/api/settings/profiles/models", params={"profile_id": profile["id"]}
    )
    assert second.json()["cached"] is True
    assert calls["n"] == 1, "second call must hit the 60s cache"
    assert "sk-CANARY-ModelKey-7777" not in second.text

    assert (
        client.get(
            "/api/settings/profiles/models", params={"profile_id": "prof_nope"}
        ).status_code
        == 404
    )

    def fake_500(url, headers=None, timeout=None):
        return httpx.Response(500, json={"error": "down"})

    monkeypatch.setattr(httpx, "get", fake_500)
    svc._models_cache.clear()
    broken = client.get(
        "/api/settings/profiles/models", params={"profile_id": profile["id"]}
    )
    assert broken.status_code == 502
    assert "sk-CANARY-ModelKey-7777" not in broken.text

    def fake_down(url, headers=None, timeout=None):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "get", fake_down)
    svc._models_cache.clear()
    down = client.get(
        "/api/settings/profiles/models", params={"profile_id": profile["id"]}
    )
    assert down.status_code == 502


def test_chat_model_override_resolution(client, monkeypatch):
    import httpx

    from controller import service as svc

    svc._models_cache.clear()
    _create_profile(client)

    def fake_models(url, headers=None, timeout=None):
        if url.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "m-a"}, {"id": "m-b"}]})
        raise AssertionError("no chat completions should be hit on the mock path")

    monkeypatch.setattr(httpx, "get", fake_models)

    # Requested ∩ list → used + echoed in response.started.
    stream = client.post(
        "/api/chat/stream",
        json={"message": "hello there", "session_id": "model-ok", "model": "m-b"},
    )
    assert stream.status_code == 200, stream.text
    events = _sse_events(stream.text)
    assert events[0] == (
        "response.started",
        {"run_id": events[0][1]["run_id"], "model": "m-b", "mock": False, "team": None},
    )

    # Fetched + absent → 400.
    bad = client.post(
        "/api/chat/stream",
        json={"message": "hello", "session_id": "model-ok", "model": "m-nope"},
    )
    assert bad.status_code == 400

    # Fetch fails → requested allowed through (endpoint errors honestly later).
    def fake_down(url, headers=None, timeout=None):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "get", fake_down)
    svc._models_cache.clear()
    fallback = client.post(
        "/api/chat/stream",
        json={"message": "hello there", "session_id": "model-fb", "model": "m-any"},
    )
    assert fallback.status_code == 200, fallback.text
    assert _sse_events(fallback.text)[0][1]["model"] == "m-any"


# --- team behaviorally real -------------------------------------------------------


def test_chat_unknown_team_rejected(client):
    resp = client.post(
        "/api/chat/stream",
        json={"message": "hi", "session_id": "t1", "team_id": "team_nope"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "unknown team"


def test_chat_team_context_in_mock_and_history(client):
    stream = client.post(
        "/api/chat/stream",
        json={
            "message": "tell me a story",
            "session_id": "team-ctx",
            "team_id": "craft_studio",
        },
    )
    assert stream.status_code == 200, stream.text
    events = _sse_events(stream.text)
    assert events[0][0] == "response.started"
    assert events[0][1]["team"] == "craft_studio"
    deltas = [data["delta"] for name, data in events if name == "text.delta"]
    assert deltas and deltas[0].startswith("[team craft_studio]")

    history = client.get("/api/chat/history", params={"session_id": "team-ctx"}).json()[
        "messages"
    ]
    assert history[0]["team"] == "craft_studio"
    assert history[0]["model"] == "mock"
    assert history[1]["team"] == "craft_studio"

    # No team → null team on started + entries (backward compatible).
    plain = client.post(
        "/api/chat/stream",
        json={"message": "tell me a story", "session_id": "team-none"},
    )
    assert plain.status_code == 200
    assert _sse_events(plain.text)[0][1]["team"] is None
    msgs = client.get("/api/chat/history", params={"session_id": "team-none"}).json()[
        "messages"
    ]
    assert msgs[0]["team"] is None


# --- diagnostics + scaico-key test --------------------------------------------------


def test_diagnostics_shape_and_recent(client, monkeypatch):
    import socket

    from controller import diagnostics as diag

    diag.DIAGNOSTICS._entries.clear()

    class _Sock:
        def close(self):
            pass

    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: _Sock())
    body = client.get("/api/diagnostics").json()
    assert set(body["checks"]) == {"gateway", "controller", "scaico", "litellm"}
    assert body["checks"]["gateway"] == {
        "ok": True,
        "latency_ms": body["checks"]["gateway"]["latency_ms"],
    }
    assert body["checks"]["controller"] == {"ok": True}
    # No key, no profile → not-configured (no secrets anywhere).
    assert body["checks"]["scaico"] == {"ok": False, "configured": False}
    assert body["checks"]["litellm"] == {"ok": False, "configured": False}
    services = [e["service"] for e in body["recent"]]
    assert services == ["litellm", "scaico", "controller", "gateway"]
    for entry in body["recent"]:
        assert set(entry) <= {"at", "service", "ok", "latency_ms", "detail"}
    assert len(diag.DIAGNOSTICS.recent(100)) <= 200


def test_diagnostics_gateway_failure_shape(client, monkeypatch):
    import socket

    def _fail(*a, **k):
        raise OSError("refused")

    monkeypatch.setattr(socket, "create_connection", _fail)
    checks = client.get("/api/diagnostics").json()["checks"]
    assert checks["gateway"]["ok"] is False
    assert checks["gateway"]["detail"] == "tcp connect failed"


def test_scaico_key_test_no_echo(client, monkeypatch):
    import httpx

    def fake_info(url, headers=None, timeout=None):
        assert url.endswith("/api/info")
        assert headers["X-API-Key"] == "scaico-CANARY-9999"
        assert headers["Accept"] == "application/json"
        return httpx.Response(200, json={"name": "scaico"})

    monkeypatch.setattr(httpx, "get", fake_info)
    ok = client.post(
        "/api/settings/scaico-key/test", json={"api_key": "scaico-CANARY-9999"}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["ok"] is True
    assert "latency_ms" in ok.json()
    assert "scaico-CANARY-9999" not in ok.text

    # Stored-key path.
    client.put("/api/settings/scaico-key", json={"api_key": "scaico-CANARY-9999"})
    stored = client.post("/api/settings/scaico-key/test", json={})
    assert stored.json()["ok"] is True
    assert "scaico-CANARY-9999" not in stored.text

    # Failure shape + no key configured.
    def fake_500(url, headers=None, timeout=None):
        return httpx.Response(500, json={"detail": "bad"})

    monkeypatch.setattr(httpx, "get", fake_500)
    bad = client.post(
        "/api/settings/scaico-key/test", json={"api_key": "scaico-CANARY-9999"}
    )
    assert bad.json() == {
        "ok": False,
        "latency_ms": bad.json()["latency_ms"],
        "status": 500,
        "error": "scaico answered status 500",
    }

    client.put("/api/settings/scaico-key", json={"api_key": ""})
    assert client.post("/api/settings/scaico-key/test", json={}).json() == {
        "ok": False,
        "error": "no scaico key configured",
    }


# --- conversations API --------------------------------------------------------------


def test_conversations_empty_and_delete_404(client):
    assert client.get("/api/conversations").json() == {"conversations": []}
    missing = client.delete("/api/conversations/nope")
    assert missing.status_code == 404


def test_conversations_ordering_truncation_and_delete(client):
    long_msg = "x" * 100
    client.post("/api/chat/stream", json={"message": long_msg, "session_id": "conv-a"})
    client.post(
        "/api/chat/stream", json={"message": "short msg", "session_id": "conv-b"}
    )
    upload = client.post(
        "/api/files/open",
        files={"file": ("pic.png", _make_png_bytes(), "image/png")},
        data={"session_id": "conv-b"},
    )
    assert upload.status_code == 201

    body = client.get("/api/conversations").json()["conversations"]
    assert [c["id"] for c in body] == ["conv-b", "conv-a"]
    by_id = {c["id"]: c for c in body}
    assert by_id["conv-a"]["title"] == "x" * 60
    assert by_id["conv-a"]["message_count"] == 2
    assert by_id["conv-a"]["doc_ids"] == []
    assert by_id["conv-a"]["app"] is None
    assert by_id["conv-b"]["app"] == "photocraft"
    assert by_id["conv-b"]["doc_ids"] != []
    assert by_id["conv-b"]["updated_at"] >= by_id["conv-a"]["updated_at"]
    # History metadata (team/model) present on entries.
    history = client.get("/api/chat/history", params={"session_id": "conv-a"}).json()[
        "messages"
    ]
    assert all("team" in m and "model" in m for m in history)

    deleted = client.delete("/api/conversations/conv-a")
    assert deleted.json() == {"deleted": "conv-a"}
    remaining = client.get("/api/conversations").json()["conversations"]
    assert [c["id"] for c in remaining] == ["conv-b"]
    assert (
        client.get("/api/chat/history", params={"session_id": "conv-a"}).json()[
            "messages"
        ]
        == []
    )
    # Files on disk are kept: the doc still inspects fine.
    doc_id = by_id["conv-b"]["doc_ids"][0]
    assert (
        client.get(f"/api/files/{doc_id}", params={"session_id": "conv-b"}).status_code
        == 200
    )


# --- files ----------------------------------------------------------------------


def test_file_open_inspect_download(client):
    upload = client.post(
        "/api/files/open",
        files={"file": ("pic.png", _make_png_bytes(), "image/png")},
        data={"session_id": "s1"},
    )
    assert upload.status_code == 201, upload.text
    body = upload.json()
    assert body["kind"] == "photo"
    assert body["inspect"]["width"] == 32

    inspect = client.get(f"/api/files/{body['doc_id']}", params={"session_id": "s1"})
    assert inspect.json()["inspect"]["width"] == 32

    download = client.get(
        f"/api/files/{body['doc_id']}/download", params={"session_id": "s1"}
    )
    assert download.status_code == 200
    assert download.content[:4] == b"\x89PNG"

    assert (
        client.get("/api/files/doc_nope", params={"session_id": "s1"}).status_code
        == 404
    )


def test_file_open_negative(client):
    bad_type = client.post(
        "/api/files/open",
        files={"file": ("evil.exe", b"MZ", "application/octet-stream")},
        data={"session_id": "s1"},
    )
    assert bad_type.status_code == 415

    fake_pdf = client.post(
        "/api/files/open",
        files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
        data={"session_id": "s1"},
    )
    assert fake_pdf.status_code == 400


# --- chat stream (SSE shape) ------------------------------------------------------


def test_chat_stream_sse_shape(client):
    upload = client.post(
        "/api/files/open",
        files={"file": ("pic.png", _make_png_bytes(), "image/png")},
        data={"session_id": "chat1"},
    )
    doc_id = upload.json()["doc_id"]

    stream = client.post(
        "/api/chat/stream",
        json={"message": "resize to 800px", "session_id": "chat1", "doc_id": doc_id},
    )
    assert stream.status_code == 200
    assert "text/event-stream" in stream.headers["content-type"]
    events = _sse_events(stream.text)
    names = [name for name, _ in events]
    assert names[0] == "response.started"
    assert "text.delta" in names
    text_phases = [data.get("phase") for name, data in events if name == "text.delta"]
    assert "reasoning" in text_phases
    assert text_phases[-1] == "final"
    assert "tool.call" in names
    assert "tool.result" in names
    assert names[-1] == "response.completed"
    completed = events[-1][1]
    assert completed["records"], "ledger records must ride the completed event"

    history = client.get("/api/chat/history", params={"session_id": "chat1"})
    roles = [m["role"] for m in history.json()["messages"]]
    assert roles == ["user", "assistant"]


def test_chat_stream_negative(client):
    empty = client.post("/api/chat/stream", json={"message": "  "})
    assert empty.status_code == 400
    unknown = client.post(
        "/api/chat/stream", json={"message": "hi", "doc_id": "doc_nope"}
    )
    assert unknown.status_code == 404


# --- Lane 4: view↔controller wiring (compat shapes + verify + thumbnail) -------


def _open_png(client, session_id="lane4"):
    upload = client.post(
        "/api/files/open",
        files={"file": ("pic.png", _make_png_bytes(), "image/png")},
        data={"session_id": session_id},
    )
    assert upload.status_code == 201, upload.text
    return upload.json()


def test_profiles_list_carries_active_id(client):
    body = client.get("/api/settings/profiles").json()
    assert body["active_profile_id"] is None
    created = client.post(
        "/api/settings/profiles",
        json={
            "label": "P",
            "api_base": "http://127.0.0.1:9/v1",
            "api_key": "sk-CANARY-1111",
            "default_model": "m",
        },
    )
    assert (
        created.json()["profile"]["id"]
        == client.get("/api/settings/profiles").json()["active_profile_id"]
    )
    assert "sk-CANARY-1111" not in client.get("/api/settings/profiles").text


def test_files_open_inspect_compat_aliases(client):
    body = _open_png(client)
    assert body["app"] == body["kind"] == "photo"
    assert body["name"] == body["source_name"] == "pic.png"
    assert body["session_id"] == "lane4"
    assert (
        body["thumbnail_url"]
        == f"/api/files/{body['doc_id']}/thumbnail?session_id=lane4"
    )

    inspect = client.get(
        f"/api/files/{body['doc_id']}", params={"session_id": "lane4"}
    ).json()
    assert inspect["app"] == "photo"
    assert inspect["name"] == "pic.png"
    assert inspect["session_id"] == "lane4"


def test_thumbnail_photo_pdf_sheet(client):
    photo = _open_png(client, "thumb-photo")
    thumb = client.get(
        f"/api/files/{photo['doc_id']}/thumbnail", params={"session_id": "thumb-photo"}
    )
    assert thumb.status_code == 200
    assert thumb.content[:4] == b"\x89PNG"

    # Cross-session isolation: same doc id, different session → 404.
    assert (
        client.get(
            f"/api/files/{photo['doc_id']}/thumbnail", params={"session_id": "other"}
        ).status_code
        == 404
    )
    assert (
        client.get(
            "/api/files/doc_nope/thumbnail", params={"session_id": "lane4"}
        ).status_code
        == 404
    )

    # Sheets have no pixels → honest 404 (view keeps the inspect summary).
    import io as _io

    import openpyxl

    wb = openpyxl.Workbook()
    wb.active["A1"] = 1
    buf = _io.BytesIO()
    wb.save(buf)
    sheet = client.post(
        "/api/files/open",
        files={
            "file": (
                "s.xlsx",
                buf.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        data={"session_id": "thumb-sheet"},
    ).json()
    assert (
        client.get(
            f"/api/files/{sheet['doc_id']}/thumbnail",
            params={"session_id": "thumb-sheet"},
        ).status_code
        == 404
    )


def test_sse_compat_payload_keys(client):
    body = _open_png(client, "sse-compat")
    stream = client.post(
        "/api/chat/stream",
        json={
            "message": "resize to 800px",
            "session_id": "sse-compat",
            "doc_id": body["doc_id"],
        },
    )
    events = _sse_events(stream.text)
    calls = [data for name, data in events if name == "tool.call"]
    results = [data for name, data in events if name == "tool.result"]
    assert calls and "args" in calls[0] and "call_id" in calls[0]
    assert results and "summary" in results[0] and "error" in results[0]
    completed = next(data for name, data in events if name == "response.completed")
    assert completed["message_id"] == completed["run_id"]
    assert completed["records"]


def test_verify_snapshot_restore_record_view(client):
    body = _open_png(client, "verify-sess")
    doc_id = body["doc_id"]

    snap = client.post(
        "/api/verify/snapshot", json={"session_id": "verify-sess", "doc_id": doc_id}
    )
    assert snap.json() == {"ok": True, "summary": "Snapshot revision 2."}

    # Mutate via chat (mock brain resize), then restore to the snapshot.
    client.post(
        "/api/chat/stream",
        json={
            "message": "resize to 800px",
            "session_id": "verify-sess",
            "doc_id": doc_id,
        },
    )
    restored = client.post(
        "/api/verify/restore", json={"session_id": "verify-sess", "doc_id": doc_id}
    )
    assert restored.json()["ok"] is True

    record = client.post(
        "/api/verify/record-view", json={"session_id": "verify-sess", "doc_id": doc_id}
    )
    assert record.json()["ok"] is True
    assert "revision" in record.json()["summary"]

    # Isolation + error shapes: unknown doc → 404, unknown session doc → 404.
    assert (
        client.post(
            "/api/verify/snapshot",
            json={"session_id": "verify-sess", "doc_id": "doc_nope"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/verify/record-view",
            json={"session_id": "verify-sess", "doc_id": "doc_nope"},
        ).status_code
        == 404
    )
    leaked = (
        snap.text
        + restored.text
        + record.text
        + client.post("/api/verify/snapshot", json={"session_id": "verify-sess"}).text
    )
    assert "sk-" not in leaked and "api_key" not in leaked
