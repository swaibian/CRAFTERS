"""Live desktop apps as chat objects (controller side).

Positive: env parsing (fault-isolated, pdfcraft skipped), status
up/down/unconfigured, document listing against a real wire-format stub
(gridcraft-style no-auth + photocraft-style token auth), attach → 201 with
live provenance → thumbnail 200 → mock chat stream completes on the
attached doc. LiveExecutor + the live agent lane: activate-first commands,
inspect/look/save against the stub, path containment, and the live chat
stream running real commands on the open app.
Negative: malformed env var, refused port, wrong token, unknown app,
unknown document index, occluded window (no image payload), escaping
save paths, command errors truncated, bridge down → honest error (no
adapter fallback).
"""

from __future__ import annotations

import base64
import io
import json
import os
import socket
import tempfile
import threading
from pathlib import Path

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

DOC_INSPECT = {
    "width": 48,
    "height": 32,
    "layers": [
        {
            "id": 0,
            "name": "Background",
            "kind": "raster",
            "blend": "Normal",
            "opacity": 1.0,
        },
        {
            "id": 1,
            "name": "copy",
            "kind": "raster",
            "blend": "Screen",
            "opacity": 0.8,
        },
    ],
    "history": [{"name": "open"}, {"name": "rotate"}, {"name": "blur"}],
}


class LiveStubServer:
    """Threaded stand-in for a desktop app's control channel.

    Speaks the real wire format (one ``{"id","method","params"}`` line in,
    one ``{"id","ok","result"}`` line out; optional photocraft-style auth
    frame first). Each connection runs on its own thread; ``activate_calls``
    records ``document.activate`` targets, ``execute_calls`` other
    ``engine.execute`` commands, ``command_list_calls`` ``engine.commands``
    filters, and ``save_calls`` ``app.save`` paths.
    """

    def __init__(
        self,
        *,
        require_token=None,
        screenshot_b64=PNG_B64,
        command_errors=None,
        ui_inspect=None,
        document_inspect=None,
    ):
        self._require_token = require_token
        self._screenshot_b64 = screenshot_b64
        self._command_errors = dict(command_errors or {})
        self._ui_inspect = ui_inspect if ui_inspect is not None else SESSION_INSPECT
        self._document_inspect = document_inspect if document_inspect is not None else DOC_INSPECT
        self._mutations: list = []
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        self._sock.settimeout(0.5)
        self._stop = threading.Event()
        self.activate_calls: list = []
        self.execute_calls: list = []
        self.command_list_calls: list = []
        self.save_calls: list = []
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
        if method == "engine.execute":
            command = params.get("command")
            if command in {"document.activate", "window.activate"}:
                inner = params.get("params") or {}
                self.activate_calls.append(inner.get("document", inner.get("index")))
                return {"id": msg.get("id"), "ok": True, "result": {}}
            if command in self._command_errors:
                return {
                    "id": msg.get("id"),
                    "ok": False,
                    "error": self._command_errors[command],
                }
            self.execute_calls.append((command, params.get("params") or {}))
            if command == "document.inspect":
                # Honest engine model: history grows with every applied
                # command, so before/after diffs can prove an edit landed.
                info = dict(DOC_INSPECT)
                info["history"] = DOC_INSPECT["history"] + [
                    {"name": name} for name in self._mutations
                ]
                return {"id": msg.get("id"), "ok": True, "result": info}
            self._mutations.append(command)
            return {
                "id": msg.get("id"),
                "ok": True,
                "result": {"name": "second.psd", "width": 48, "height": 32},
            }
        result: object = {}
        if method == "ui.inspect":
            result = self._ui_inspect
        elif method == "document.inspect":
            result = self._document_inspect
        elif method == "ui.screenshot":
            result = {"image": self._screenshot_b64} if self._screenshot_b64 else {}
        elif method == "engine.commands":
            self.command_list_calls.append(params.get("filter"))
            # Real shape: `engine.commands` answers a bare JSON array
            # (crates/engine `command.list`), never an envelope object.
            result = [
                {"id": "image.imageRotation.90cw"},
                {"id": "image.adjustments.desaturate"},
            ]
        elif method == "app.save":
            self.save_calls.append(params.get("path"))
            result = {"path": params.get("path") or "second.psd", "warnings": []}
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


def _sse_events(text):
    events = []
    for block in text.strip().split("\n\n"):
        name = ""
        data = {}
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line.split(": ", 1)[1]
            elif line.startswith("data: "):
                data = json.loads(line.split(": ", 1)[1])
        if name:
            events.append((name, data))
    return events


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
        assert body == {
            "app": "gridcraft",
            "running": True,
            "mode": "bridge",
            "pid": 4242,
        }
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
    assert token_file.startswith(
        os.path.join(tempfile.gettempdir(), "crafter-photocraft-")
    )
    mode = stat.S_IMODE(os.stat(token_file).st_mode)
    assert mode == 0o600, oct(mode)


def test_launch_already_running_skips_spawn(tmp_path, monkeypatch):
    import asyncio

    import controller.live as live_mod
    from controller.live import LiveManager, launch_app

    async def go():
        with LiveStubServer() as stub:
            manager = LiveManager(
                bridges={"gridcraft": _bridge("gridcraft", stub.port)}
            )

            def boom(*args, **kwargs):  # pragma: no cover - must not spawn
                raise AssertionError("spawn called for a running app")

            with monkeypatch.context() as m:
                m.setattr(
                    live_mod,
                    "LAUNCH_PORTS",
                    {"photocraft": 7878, "gridcraft": stub.port},
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


def test_detached_kwargs_match_platform(monkeypatch):
    import sys

    import controller.live as live_mod

    monkeypatch.setattr(sys, "platform", "win32")
    # Simulate the Windows-only creation flags (absent on macOS/Linux).
    monkeypatch.setattr(live_mod.subprocess, "DETACHED_PROCESS", 0x8, raising=False)
    monkeypatch.setattr(
        live_mod.subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200, raising=False
    )
    win_flags = live_mod._detached_kwargs()
    assert "creationflags" in win_flags and "start_new_session" not in win_flags
    assert win_flags["creationflags"] == 0x8 | 0x200

    monkeypatch.setattr(sys, "platform", "darwin")
    posix_flags = live_mod._detached_kwargs()
    assert posix_flags == {"start_new_session": True}

    monkeypatch.setattr(sys, "platform", "linux")
    assert live_mod._detached_kwargs() == {"start_new_session": True}


def test_resolve_desktop_binary_prefers_explicit_env(tmp_path, monkeypatch):
    from controller.live import resolve_desktop_binary

    exe = tmp_path / "photocraft"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    monkeypatch.setenv("CRAFTER_DESKTOP_PHOTOCRAFT", str(exe))
    assert resolve_desktop_binary("photocraft") == str(exe)
    # Non-executable explicit path resolves to None (never falls to PATH).
    other = tmp_path / "nope"
    other.write_text("x")
    other.chmod(0o644)
    monkeypatch.setenv("CRAFTER_DESKTOP_PHOTOCRAFT", str(other))
    monkeypatch.setenv("PATH", str(tmp_path))
    assert resolve_desktop_binary("photocraft") is None
    assert resolve_desktop_binary("pdfcraft") is None


def test_screenshot_prefers_capture_file(tmp_path, monkeypatch):
    """Regression (live 500): full-window base64 replies exceed the 8 MiB
    control-channel ceiling. The capture must go to {"path"} inside the
    launch-recorded root and the temp file must be cleaned up."""
    import asyncio

    import controller.live as live_mod
    from controller.live import LiveManager

    root = tmp_path / "desktops"
    root.mkdir()
    calls: list = []

    async def fake_call(self, app, method, params):
        assert method == "ui.screenshot"
        calls.append(dict(params))
        assert params["path"].startswith(str(root))
        Path(params["path"]).write_bytes(PNG_BYTES)
        return {"path": params["path"], "width": 48, "height": 32}

    async def go():
        manager = LiveManager(bridges={}, roots={"photocraft": str(root)})
        with monkeypatch.context() as m:
            m.setattr(LiveManager, "_call", fake_call)
            assert live_mod._read_png_file(str(root / "junk.bin")) is None
            png = await manager.screenshot_png("photocraft")
        assert png == PNG_BYTES
        leftovers = [p for p in root.iterdir() if p.name.startswith("crafter-shot-")]
        assert leftovers == []
        assert calls and "path" in calls[0]

    asyncio.run(go())


def test_screenshot_falls_back_to_base64(tmp_path, monkeypatch):
    """Manually started apps (unknown roots) reject the temp path — the
    small-window base64 reply still works."""
    import asyncio
    import base64

    from controller.live import LiveError, LiveManager

    async def fake_call(self, app, method, params):
        if params.get("path"):
            raise LiveError("automation write authority is not configured")
        return {"image": base64.b64encode(PNG_BYTES).decode("ascii")}

    async def go():
        manager = LiveManager(bridges={})
        with monkeypatch.context() as m:
            m.setattr(LiveManager, "_call", fake_call)
            assert await manager.screenshot_png("photocraft") == PNG_BYTES

    asyncio.run(go())


def test_launch_records_roots_for_screenshots(tmp_path, monkeypatch):
    """launch_app stores the automation root so screenshot_png can aim
    its capture file inside the write authority."""
    import asyncio
    import types

    import controller.live as live_mod
    from controller.live import LiveManager, launch_app

    _fake_binary(tmp_path, monkeypatch, "gridcraft")

    def fake_spawn(argv, **kwargs):
        return types.SimpleNamespace(pid=7)

    async def go():
        with LiveStubServer() as stub:
            manager = LiveManager(bridges={})
            with monkeypatch.context() as m:
                m.setattr(live_mod.subprocess, "Popen", fake_spawn)
                m.setattr(
                    live_mod,
                    "LAUNCH_PORTS",
                    {"photocraft": 7878, "gridcraft": stub.port},
                )
                await launch_app(manager, "gridcraft", timeout_s=5.0)
            assert manager.roots["gridcraft"] == str(tmp_path / "desktops")

    asyncio.run(go())


# --- LiveExecutor: the live lane's command surface -----------------------------


def test_executor_execute_activates_then_runs():
    import asyncio

    from controller.live import LiveError, LiveExecutor

    async def go():
        with LiveStubServer() as stub:
            manager = LiveManager(
                bridges={"photocraft": _bridge("photocraft", stub.port)}
            )
            executor = LiveExecutor(manager=manager, app="photocraft", document=1)
            result = await executor.execute("image.imageRotation.90cw", {"angle": 90})
            assert result["width"] == 48
            assert stub.activate_calls == [1]
            assert stub.execute_calls == [("image.imageRotation.90cw", {"angle": 90})]
            # No linked index → no document.activate step.
            plain = LiveExecutor(manager=manager, app="photocraft")
            await plain.execute("image.imageRotation.180")
            assert stub.activate_calls == [1]
            assert stub.execute_calls[-1] == ("image.imageRotation.180", {})
            try:
                await executor.execute("   ")
            except LiveError as exc:
                assert "command id" in str(exc)
            else:  # pragma: no cover
                raise AssertionError("expected LiveError")

    asyncio.run(go())


def test_executor_commands_inspect_look_and_save():
    import asyncio

    from controller.live import LiveExecutor

    async def go():
        with LiveStubServer() as stub:
            executor = LiveExecutor(
                manager=LiveManager(
                    bridges={"photocraft": _bridge("photocraft", stub.port)}
                ),
                app="photocraft",
                document=1,
            )
            listing = await executor.commands("rotate")
            assert [c["id"] for c in listing["commands"]]
            assert stub.command_list_calls == ["rotate"]
            assert (await executor.commands())["commands"]
            assert stub.command_list_calls[-1] is None
            info = await executor.inspect()
            assert info == DOC_INSPECT
            assert stub.execute_calls == [("document.inspect", {})]
            assert (await executor.look()) == PNG_BYTES
            saved = await executor.save("out/deep.png")
            assert saved["path"] == "out/deep.png"
            assert stub.save_calls == ["out/deep.png"]
            await executor.save(None)
            assert stub.save_calls[-1] is None

    asyncio.run(go())


def test_executor_save_rejects_escaping_paths():
    import asyncio

    from controller.live import LiveError, LiveExecutor

    async def go():
        with LiveStubServer() as stub:
            executor = LiveExecutor(
                manager=LiveManager(
                    bridges={"photocraft": _bridge("photocraft", stub.port)}
                ),
                app="photocraft",
            )
            bad_paths = (
                "",
                "   ",
                "../evil.png",
                "out/../../evil.png",
                "/tmp/evil.png",
                "C:/evil.png",
                "~/evil.png",
                "a//b.png",
                "a/./b.png",
                "back\\slash.png",
            )
            for bad in bad_paths:
                try:
                    await executor.save(bad)
                except LiveError as exc:
                    assert str(exc).startswith("doc_save path"), (bad, str(exc))
                else:  # pragma: no cover
                    raise AssertionError(f"expected LiveError for {bad!r}")
            assert stub.save_calls == []

    asyncio.run(go())


def test_executor_down_app_is_honest():
    import asyncio

    from controller.live import LiveError, LiveExecutor

    async def go():
        executor = LiveExecutor(
            manager=LiveManager(bridges={}), app="photocraft", document=0
        )
        attempts = (
            executor.execute("image.imageRotation.90cw"),
            executor.commands(),
            executor.inspect(),
            executor.save("out.png"),
            executor.look(),
        )
        for attempt in attempts:
            try:
                await attempt
            except LiveError as exc:
                assert str(exc) == (
                    "photocraft is not running — start it from the App panel or Refresh"
                )
            else:  # pragma: no cover
                raise AssertionError("expected LiveError")

    asyncio.run(go())


def test_executor_command_error_keeps_truncated_app_text():
    import asyncio

    from controller.live import LiveError, LiveExecutor

    long_error = "command refused: " + "x" * 400

    async def go():
        with LiveStubServer(
            command_errors={"image.adjustments.desaturate": long_error}
        ) as stub:
            executor = LiveExecutor(
                manager=LiveManager(
                    bridges={"photocraft": _bridge("photocraft", stub.port)}
                ),
                app="photocraft",
            )
            try:
                await executor.execute("image.adjustments.desaturate")
            except LiveError as exc:
                message = str(exc)
                assert "engine.execute failed: command refused" in message
                assert len(message) <= 230
            else:  # pragma: no cover
                raise AssertionError("expected LiveError")

    asyncio.run(go())


# --- agent loop on the live lane ------------------------------------------------


def test_loop_live_rotate_hits_the_open_app(tmp_path):
    import asyncio

    from controller.agent import brain_from_profile, run_agent_loop
    from controller.commands import CommandCatalog
    from controller.documents import DocumentRegistry
    from controller.live import LiveExecutor
    from controller.llm import MockBrain

    async def go():
        with LiveStubServer() as stub:
            executor = LiveExecutor(
                manager=LiveManager(
                    bridges={"photocraft": _bridge("photocraft", stub.port)}
                ),
                app="photocraft",
                document=1,
            )
            catalog = CommandCatalog((await executor.commands())["commands"])
            plan_fn, model, is_mock = brain_from_profile(
                None,
                MockBrain(catalog=catalog),
                live=True,
                live_app="photocraft",
            )
            events = [
                event
                async for event in run_agent_loop(
                    "rotate the picture clockwise",
                    doc_id=None,
                    registry=DocumentRegistry(tmp_path / "work"),
                    plan_fn=plan_fn,
                    model_name=model,
                    is_mock=is_mock,
                    executor=executor,
                    live_app="photocraft",
                    catalog=catalog,
                )
            ]
            types = [e["type"] for e in events]
            assert types[0] == "run.started" and types[-1] == "run.completed"
            assert "tool.call" in types and "tool.result" in types
            assert "observe" in types and "record" in types
            calls = [e for e in events if e["type"] == "tool.call"]
            assert calls[0]["name"] == "command_run"
            assert calls[0]["arguments"] == {"command": "image.imageRotation.90cw"}
            assert calls[-1]["name"] == "done"
            results = [e for e in events if e["type"] == "tool.result"]
            assert results[0]["ok"] is True
            observed = next(e for e in events if e["type"] == "observe")
            assert observed["observation"]["kind"] == "live"
            assert observed["observation"]["app"] == "photocraft"
            detail = observed["observation"]["detail"]
            assert detail["layer_tree"][0]["id"] == 0
            assert {k: v for k, v in detail.items() if k != "layer_tree"} == {
                "width": 48,
                "height": 32,
                "layers": 2,
                "layer_summary": [
                    "Background (raster, Normal, 100%)",
                    "copy (raster, Screen, 80%)",
                ],
                "history": 4,  # 3 base entries + the rotation that just ran
            }
            # Baseline observe before the edit → the after-observe proves it.
            assert observed["changed"] is True
            assert observed["observation"]["revision"] == 4
            assert observed["observation"]["content_hash"].startswith("sha256:")
            assert stub.activate_calls == [1, 1, 1]
            assert stub.execute_calls == [
                ("document.inspect", {}),
                ("image.imageRotation.90cw", {}),
                ("document.inspect", {}),
            ]
            completed = events[-1]
            assert "image.imageRotation.90cw" in completed["summary"]
            assert completed["records"]

    asyncio.run(go())


def test_loop_live_bridge_failure_stops_honestly(tmp_path):
    import asyncio

    from controller.agent import brain_from_profile, run_agent_loop
    from controller.commands import CommandCatalog
    from controller.documents import DocumentRegistry
    from controller.live import LiveExecutor
    from controller.llm import MockBrain

    async def go():
        executor = LiveExecutor(
            manager=LiveManager(bridges={}), app="photocraft", document=1
        )
        catalog = CommandCatalog(
            [
                {
                    "id": "image.imageRotation.90cw",
                    "label": "90° Clockwise",
                    "params": "{}",
                }
            ]
        )
        plan_fn, model, is_mock = brain_from_profile(
            None,
            MockBrain(catalog=catalog),
            live=True,
            live_app="photocraft",
        )
        events = [
            event
            async for event in run_agent_loop(
                "rotate the picture clockwise",
                doc_id=None,
                registry=DocumentRegistry(tmp_path / "work"),
                plan_fn=plan_fn,
                model_name=model,
                is_mock=is_mock,
                executor=executor,
                live_app="photocraft",
                catalog=catalog,
            )
        ]
        results = [e for e in events if e["type"] == "tool.result"]
        assert results[0]["name"] == "command_run"
        assert results[0]["ok"] is False
        assert "is not running" in results[0]["error"]
        assert events[-1]["type"] == "run.completed"
        assert "could not complete" in events[-1]["summary"]

    asyncio.run(go())


# --- chat stream on the live lane ----------------------------------------------


def test_chat_stream_live_runs_command_on_the_open_app(tmp_path, monkeypatch):
    with LiveStubServer() as stub:
        client = _client(
            tmp_path, monkeypatch, {"gridcraft": _bridge("gridcraft", stub.port)}
        )
        attached = client.post(
            "/api/live/attach",
            json={"session_id": "live-chat", "app": "gridcraft", "document": 1},
        )
        assert attached.status_code == 201, attached.text
        stream = client.post(
            "/api/chat/stream",
            json={
                "session_id": "live-chat",
                "doc_id": attached.json()["doc_id"],
                "message": "rotate the picture clockwise",
            },
        )
        assert stream.status_code == 200, stream.text
        events = _sse_events(stream.text)
        names = [name for name, _ in events]
        assert names[0] == "response.started" and names[-1] == "response.completed"
        calls = [data for name, data in events if name == "tool.call"]
        assert calls[0]["name"] == "command_run"
        assert calls[0]["args"] == {"command": "image.imageRotation.90cw"}
        results = [data for name, data in events if name == "tool.result"]
        assert results[0]["ok"] is True
        assert stub.activate_calls and all(i == 1 for i in stub.activate_calls)
        assert ("image.imageRotation.90cw", {}) in stub.execute_calls


def test_chat_stream_live_bridge_down_is_honest_error(tmp_path, monkeypatch):
    with LiveStubServer() as stub:
        client = _client(
            tmp_path, monkeypatch, {"gridcraft": _bridge("gridcraft", stub.port)}
        )
        attached = client.post(
            "/api/live/attach",
            json={"session_id": "live-down", "app": "gridcraft", "document": 1},
        )
        assert attached.status_code == 201, attached.text
        doc_id = attached.json()["doc_id"]
    # The app went away after the attach: the chat must fail honestly and
    # never fall back to editing the imported copy.
    stream = client.post(
        "/api/chat/stream",
        json={
            "session_id": "live-down",
            "doc_id": doc_id,
            "message": "rotate the picture clockwise",
        },
    )
    events = _sse_events(stream.text)
    names = [name for name, _ in events]
    assert names == ["response.error"]
    errors = [data for name, data in events if name == "response.error"]
    assert "is not running" in errors[0]["message"]
    assert not [data for name, data in events if name == "tool.call"]
