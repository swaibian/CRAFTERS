"""Live desktop apps as chat objects (controller side).

Positive: env parsing (fault-isolated, pdfcraft skipped), status
up/down/unconfigured, document listing against a real wire-format stub
(gridcraft-style no-auth + photocraft-style token auth), attach → 201 with
live provenance → thumbnail 200 → mock chat stream completes on the
attached doc.
Negative: malformed env var, refused port, wrong token, unknown app,
unknown document index, occluded window (no image payload).
"""

from __future__ import annotations

import base64
import io
import json
import os
import socket
import tempfile
import threading

from fastapi.testclient import TestClient

from controller.live import (
    LIVE_APPS,
    LiveManager,
    live_configs_from_env,
    sanitize_filename,
)
from controller.service import ServiceState, create_app
from controller.settings import SettingsStore
from gateway.bridge import BridgeConfig


def _make_png_bytes(size=(48, 32)):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color=(200, 30, 30)).save(buf, "PNG")
    buf.seek(0)
    return buf.read()


PNG_BYTES = _make_png_bytes()
PNG_B64 = base64.b64encode(PNG_BYTES).decode("ascii")

SESSION_INSPECT = {
    "session": {
        "active": 1,
        "documents": [
            {
                "index": 0,
                "name": "first.psd",
                "width": 100,
                "height": 80,
                "dirty": False,
            },
            {
                "index": 1,
                "name": "second.psd",
                "width": 48,
                "height": 32,
                "dirty": True,
            },
        ],
    },
    "document": {"name": "second.psd", "width": 48, "height": 32},
}


class LiveStubServer:
    """Threaded stand-in for a desktop app's control channel.

    Speaks the real wire format (one ``{"id","method","params"}`` line in,
    one ``{"id","ok","result"}`` line out; optional photocraft-style auth
    frame first). Each connection runs on its own thread; ``activate_calls``
    records ``document.activate`` targets.
    """

    def __init__(self, *, require_token=None, screenshot_b64=PNG_B64):
        self._require_token = require_token
        self._screenshot_b64 = screenshot_b64
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        self._sock.settimeout(0.5)
        self._stop = threading.Event()
        self.activate_calls: list = []
        self._thread = threading.Thread(target=self._serve, daemon=True)

    @property
    def port(self):
        return self._sock.getsockname()[1]

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=5)
        self._sock.close()

    def _serve(self):
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn):
        authed = self._require_token is None
        try:
            stream = conn.makefile("rw")
            while True:
                raw = stream.readline()
                if not raw:
                    break
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    stream.write(
                        json.dumps({"ok": False, "error": "invalid JSON"}) + "\n"
                    )
                    stream.flush()
                    continue
                if not isinstance(msg, dict):
                    continue
                if not authed:
                    good = (
                        msg.get("method") == "auth"
                        and isinstance(msg.get("params"), dict)
                        and msg["params"].get("token") == self._require_token
                    )
                    authed = good
                    reply = {"id": msg.get("id"), "ok": good}
                    if not good:
                        reply["error"] = "bad token"
                    stream.write(json.dumps(reply) + "\n")
                    stream.flush()
                    continue
                stream.write(json.dumps(self._reply(msg)) + "\n")
                stream.flush()
        except (OSError, ValueError):
            pass
        finally:
            conn.close()

    def _reply(self, msg):
        method = msg.get("method")
        params = msg.get("params") or {}
        result: object = {}
        if method == "ui.inspect":
            result = SESSION_INSPECT
        elif method == "ui.screenshot":
            result = {"image": self._screenshot_b64} if self._screenshot_b64 else {}
        elif (
            method == "engine.execute" and params.get("command") == "document.activate"
        ):
            self.activate_calls.append((params.get("params") or {}).get("document"))
            result = {}
        elif method == "engine.execute":
            result = {"name": "second.psd", "width": 48, "height": 32}
        return {"id": msg.get("id"), "ok": True, "result": result}


def _bridge(app, port, token_file=None):
    return BridgeConfig(
        app=app,
        host="127.0.0.1",
        port=port,
        token_file=token_file,
        timeout_s=5.0,
        inspect_style="engine" if app == "photocraft" else "direct",
    )


def _client(tmp_path, monkeypatch, bridges):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setenv("CRAFTER_SETTINGS_FILE", str(settings_path))
    state = ServiceState(
        settings=SettingsStore(path=settings_path),
        work_root=tmp_path / "work",
        live=LiveManager(bridges=bridges),
    )
    return TestClient(create_app(state))


# --- env parsing -------------------------------------------------------------


def test_env_parsing_fault_isolated():
    env = {
        "CRAFTER_BRIDGE_PHOTOCRAFT": "not-a-port",
        "CRAFTER_BRIDGE_GRIDCRAFT": "127.0.0.1:7979",
    }
    configs = live_configs_from_env(env=env)
    assert "photocraft" not in configs
    assert configs["gridcraft"].port == 7979


def test_env_skips_pdfcraft_and_absent_apps():
    env = {"CRAFTER_BRIDGE_PDFCRAFT": "127.0.0.1:9999"}
    assert live_configs_from_env(env=env) == {}
    assert live_configs_from_env(env={}) == {}


def test_sanitize_filename():
    assert sanitize_filename("my photo/ret*ouch.psd") == "my_photo_ret_ouch.psd"
    assert sanitize_filename("") == "live"
    assert len(sanitize_filename("x" * 100)) <= 40


# --- status ------------------------------------------------------------------


def test_status_unconfigured_reports_hint():
    import asyncio

    async def go():
        manager = LiveManager(bridges={})
        for app in LIVE_APPS:
            status = await manager.status(app)
            assert status.running is False
            assert status.mode == "down"
            assert status.hint  # exact --control command, never empty

    asyncio.run(go())


def test_status_running_and_down():
    import asyncio

    async def go():
        with LiveStubServer() as stub:
            manager = LiveManager(
                bridges={"gridcraft": _bridge("gridcraft", stub.port)}
            )
            up = await manager.status("gridcraft")
            assert up.running is True and up.mode == "bridge"
            down = await manager.status("photocraft")
            assert down.running is False and "photocraft --control" in down.hint

    asyncio.run(go())


def test_status_token_auth_and_rejection(tmp_path):
    import asyncio

    async def go():
        good = tmp_path / "good.token"
        good.write_text("tok-abc", encoding="utf-8")
        bad = tmp_path / "bad.token"
        bad.write_text("tok-wrong", encoding="utf-8")
        with LiveStubServer(require_token="tok-abc") as stub:
            manager = LiveManager(
                bridges={
                    "photocraft": _bridge("photocraft", stub.port, str(good)),
                }
            )
            assert (await manager.status("photocraft")).running is True
            manager.bridges["photocraft"] = _bridge("photocraft", stub.port, str(bad))
            rejected = await manager.status("photocraft")
            assert rejected.running is False
            assert "auth" in (rejected.last_error or "").lower()

    asyncio.run(go())


# --- documents + attach over HTTP --------------------------------------------


def test_live_documents_parse_session(tmp_path, monkeypatch):
    with LiveStubServer() as stub:
        client = _client(
            tmp_path, monkeypatch, {"gridcraft": _bridge("gridcraft", stub.port)}
        )
        res = client.get("/api/live/documents", params={"app": "gridcraft"})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["active"] == 1
        assert [(d["index"], d["name"]) for d in body["documents"]] == [
            (0, "first.psd"),
            (1, "second.psd"),
        ]
        second = body["documents"][1]
        assert second["dirty"] is True and second["active"] is True
        assert body["documents"][0]["active"] is False


def test_live_status_http_shape(tmp_path, monkeypatch):
    with LiveStubServer() as stub:
        client = _client(
            tmp_path, monkeypatch, {"gridcraft": _bridge("gridcraft", stub.port)}
        )
        body = client.get("/api/live/status").json()
        by_app = {entry["app"]: entry for entry in body["apps"]}
        assert by_app["gridcraft"]["running"] is True
        assert by_app["photocraft"]["running"] is False
        assert "--control" in by_app["photocraft"]["hint"]
        assert by_app["photocraft"]["launchable"] is True
        assert by_app["gridcraft"]["launchable"] is True
        assert by_app["pdfcraft"]["launchable"] is False


def test_live_documents_down_is_502(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, {})
    res = client.get("/api/live/documents", params={"app": "photocraft"})
    assert res.status_code == 502
    assert "--control" in res.json()["detail"]


def test_live_documents_unknown_app_is_400(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, {})
    assert (
        client.get("/api/live/documents", params={"app": "nosuch"}).status_code == 400
    )


def test_attach_end_to_end_then_chat(tmp_path, monkeypatch):
    with LiveStubServer() as stub:
        client = _client(
            tmp_path, monkeypatch, {"gridcraft": _bridge("gridcraft", stub.port)}
        )
        attached = client.post(
            "/api/live/attach",
            json={"session_id": "live-s1", "app": "gridcraft", "document": 1},
        )
        assert attached.status_code == 201, attached.text
        body = attached.json()
        assert body["source"] == "live"
        assert body["live_app"] == "gridcraft"
        assert body["name"] == "second.psd (live gridcraft)"
        assert body["inspect"]["width"] == 48
        doc_id = body["doc_id"]

        thumb = client.get(
            f"/api/files/{doc_id}/thumbnail", params={"session_id": "live-s1"}
        )
        assert thumb.status_code == 200

        stream = client.post(
            "/api/chat/stream",
            json={
                "session_id": "live-s1",
                "doc_id": doc_id,
                "message": "What is this?",
            },
        )
        assert stream.status_code == 200, stream.text
        events = [
            line.split(": ", 1)[1]
            for block in stream.text.strip().split("\n\n")
            for line in block.splitlines()
            if line.startswith("event: ")
        ]
        assert events[0] == "response.started"
        assert "response.completed" in events


def test_attach_defaults_to_active_document(tmp_path, monkeypatch):
    with LiveStubServer() as stub:
        client = _client(
            tmp_path, monkeypatch, {"gridcraft": _bridge("gridcraft", stub.port)}
        )
        attached = client.post(
            "/api/live/attach", json={"session_id": "s", "app": "gridcraft"}
        )
        assert attached.status_code == 201, attached.text
        assert attached.json()["name"] == "second.psd (live gridcraft)"


def test_attach_unknown_document_is_400(tmp_path, monkeypatch):
    with LiveStubServer() as stub:
        client = _client(
            tmp_path, monkeypatch, {"gridcraft": _bridge("gridcraft", stub.port)}
        )
        res = client.post(
            "/api/live/attach",
            json={"session_id": "s", "app": "gridcraft", "document": 99},
        )
        assert res.status_code == 400


def test_attach_occluded_window_is_502(tmp_path, monkeypatch):
    with LiveStubServer(screenshot_b64=None) as stub:
        client = _client(
            tmp_path, monkeypatch, {"gridcraft": _bridge("gridcraft", stub.port)}
        )
        res = client.post(
            "/api/live/attach",
            json={"session_id": "s", "app": "gridcraft", "document": 1},
        )
        assert res.status_code == 502
        assert "occluded" in res.json()["detail"]


# --- launch ------------------------------------------------------------------


def _fake_binary(tmp_path, monkeypatch, app):
    exe = tmp_path / app
    exe.write_text("#!/bin/sh\nexec sleep 300\n")
    exe.chmod(0o755)
    monkeypatch.setenv(f"CRAFTER_DESKTOP_{app.upper()}", str(exe))
    monkeypatch.setenv("CRAFTER_DESKTOP_ROOT", str(tmp_path / "desktops"))
    return exe


def test_launch_unknown_app_is_400(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, {})
    res = client.post("/api/live/launch", json={"app": "nosuch"})
    assert res.status_code == 400


def test_launch_pdfcraft_is_409_with_hint(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, {})
    res = client.post("/api/live/launch", json={"app": "pdfcraft"})
    assert res.status_code == 409
    body = res.json()["detail"]
    assert "no TCP control channel" in body["error"]
    assert "--control" in body["hint"]


def test_launch_missing_binary_is_502(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))  # empty dir: no app on PATH
    monkeypatch.delenv("CRAFTER_DESKTOP_GRIDCRAFT", raising=False)
    client = _client(tmp_path, monkeypatch, {})
    res = client.post("/api/live/launch", json={"app": "gridcraft"})
    assert res.status_code == 502
    assert "not found" in res.json()["detail"]


def test_launch_gridcraft_spawns_fixed_argv_and_registers_bridge(tmp_path, monkeypatch):
    import types

    import controller.live as live_mod

    exe = _fake_binary(tmp_path, monkeypatch, "gridcraft")
    calls: list = []

    def fake_spawn(argv, **kwargs):
        calls.append((argv, kwargs))
        return types.SimpleNamespace(pid=4242)

    monkeypatch.setattr(live_mod.subprocess, "Popen", fake_spawn)
    with LiveStubServer() as stub:
        monkeypatch.setattr(
            live_mod, "LAUNCH_PORTS", {"photocraft": 7878, "gridcraft": stub.port}
        )
        client = _client(tmp_path, monkeypatch, {})
        res = client.post("/api/live/launch", json={"app": "gridcraft"})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body == {"app": "gridcraft", "running": True, "mode": "bridge", "pid": 4242}
        # Fixed argv: binary + --control + port only — no request data.
        assert calls and calls[0][0] == [str(exe), "--control", str(stub.port)]
        assert calls[0][1].get("start_new_session") is True
        # Status flips to running without a restart (bridge registered).
        assert client.get("/api/live/status").json()["apps"][1]["running"] is True


def test_launch_photocraft_writes_0600_token_and_fixed_argv(tmp_path, monkeypatch):
    import asyncio
    import stat
    import types

    import controller.live as live_mod
    from controller.live import LiveError, LiveManager, launch_app

    exe = _fake_binary(tmp_path, monkeypatch, "photocraft")
    calls: list = []

    def fake_spawn(argv, **kwargs):
        calls.append(argv)
        return types.SimpleNamespace(pid=99)

    async def go():
        manager = LiveManager(bridges={})
        with monkeypatch.context() as m:
            m.setattr(live_mod.subprocess, "Popen", fake_spawn)
            try:
                await launch_app(manager, "photocraft", timeout_s=0.1)
            except LiveError as exc:
                assert "still starting" in str(exc)
            else:  # pragma: no cover - nothing listens, must time out
                raise AssertionError("expected a timeout")
        return manager

    asyncio.run(go())
    argv = calls[0]
    assert argv[0] == str(exe)
    assert argv[1:3] == ["--control", "7878"]
    assert "--automation-read-root" in argv and "--automation-write-root" in argv
    token_flag = argv.index("--control-token-file")
    token_file = argv[token_flag + 1]
    assert token_file.startswith(os.path.join(tempfile.gettempdir(), "crafter-photocraft-"))
    mode = stat.S_IMODE(os.stat(token_file).st_mode)
    assert mode == 0o600, oct(mode)


def test_launch_already_running_skips_spawn(tmp_path, monkeypatch):
    import asyncio

    import controller.live as live_mod
    from controller.live import LiveManager, launch_app

    async def go():
        with LiveStubServer() as stub:
            manager = LiveManager(bridges={"gridcraft": _bridge("gridcraft", stub.port)})

            def boom(*args, **kwargs):  # pragma: no cover - must not spawn
                raise AssertionError("spawn called for a running app")

            with monkeypatch.context() as m:
                m.setattr(
                    live_mod, "LAUNCH_PORTS", {"photocraft": 7878, "gridcraft": stub.port}
                )
                m.setattr(live_mod.subprocess, "Popen", boom)
                result = await launch_app(manager, "gridcraft", timeout_s=2.0)
            assert result["running"] is True and result["pid"] is None

    asyncio.run(go())


def test_launch_argv_rejects_non_launchable(tmp_path):
    from controller.live import LiveError, desktop_launch_argv

    try:
        desktop_launch_argv("pdfcraft", token_file="t", work_root="w")
    except LiveError as exc:
        assert "no TCP control channel" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected LiveError")
