"""Lane 3 tests: bridge client + gateway wiring against a loopback stub.

The stub speaks the real control-protocol wire format (one
``{"id","method","params"}`` line in, one ``{"id","ok",...}`` line out;
optional photocraft-style auth frame first), so these tests verify the
exact bytes the gateway would exchange with a running desktop app. No
window is required; the stub's screenshot payload is a programmatically
built PNG (stdlib ``struct``/``zlib``) used only to verify hashing and
size parsing — it is test data, not a screenshot claim.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import struct
import zlib

import pytest

from gateway.backends import (
    BackendError,
    BackendManager,
    BridgeAppBackend,
)
from gateway.bridge import (
    BridgeClient,
    BridgeConfig,
    BridgeError,
    bridges_from_env,
    summarize_screenshot,
)
from gateway.tools_phase1 import Phase1Tools
from gateway.tools_phase2 import Phase2Tools


def make_png(width: int, height: int) -> bytes:
    """Build a minimal valid RGB PNG (stdlib only, deterministic)."""
    def chunk(ctype: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + ctype
            + data
            + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)
        )
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    rows = b"".join(b"\x00" + bytes(width * 3) for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


PNG_7x5 = make_png(7, 5)
PNG_B64 = base64.b64encode(PNG_7x5).decode("ascii")
PNG_SHA = hashlib.sha256(PNG_7x5).hexdigest()


class StubControlServer:
    """In-process stand-in for a desktop app's control channel.

    Gridcraft-style (no auth) by default; pass ``require_token`` for the
    photocraft-style auth-first exchange.
    """

    def __init__(self, *, require_token: str | None = None) -> None:
        self._require_token = require_token
        self.received: list[str] = []
        self._server: asyncio.Server | None = None

    @property
    def port(self) -> int:
        assert self._server is not None
        return self._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]

    async def __aenter__(self) -> StubControlServer:
        self._server = await asyncio.start_server(
            self._handle, "127.0.0.1", 0
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        assert self._server is not None
        self._server.close()
        await self._server.wait_closed()

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        authed = self._require_token is None
        try:
            while True:
                raw = await reader.readline()
                if not raw:
                    break
                try:
                    msg = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    writer.write(b'{"ok": false, "error": "invalid JSON"}\n')
                    await writer.drain()
                    continue
                if not isinstance(msg, dict):
                    continue
                self.received.append(raw.decode("utf-8").rstrip("\n"))
                if not authed:
                    good = (
                        msg.get("method") == "auth"
                        and isinstance(msg.get("params"), dict)
                        and msg["params"].get("token") == self._require_token
                    )
                    authed = good
                    reply: dict[str, object] = {"id": msg.get("id"), "ok": good}
                    if not good:
                        reply["error"] = "bad token"
                    writer.write((json.dumps(reply) + "\n").encode("utf-8"))
                    await writer.drain()
                    if not good:
                        break
                    continue
                await self._dispatch(msg, writer)
        finally:
            writer.close()

    async def _dispatch(
        self, msg: dict, writer: asyncio.StreamWriter
    ) -> None:
        mid = msg.get("id")
        method = msg.get("method")
        params = msg.get("params") or {}

        async def send(payload: dict) -> None:
            writer.write((json.dumps(payload) + "\n").encode("utf-8"))
            await writer.drain()

        if method == "ui.inspect":
            await send(
                {"id": mid, "ok": True,
                 "result": {"tool": "select", "windows": 1, "mode": "stub"}}
            )
        elif method == "engine.commands":
            await send(
                {"id": mid, "ok": True,
                 "result": {"commands": [{"id": "cell.set"}, {"id": "file.new"}]}}
            )
        elif method == "document.inspect":
            await send(
                {"id": mid, "ok": True,
                 "result": {"revision": 7,
                            "documents": [{"index": 0, "path": "book.xlsx"}]}}
            )
        elif method == "engine.execute" and params.get("command") == "document.inspect":
            await send(
                {"id": mid, "ok": True,
                 "result": {"revision": 7,
                            "documents": [{"index": 0, "path": "book.xlsx"}]}}
            )
        elif method == "engine.execute":
            await send(
                {"id": mid, "ok": True,
                 "result": {"ran": params.get("command")}}
            )
        elif method == "ui.screenshot":
            await send(
                {"id": mid, "ok": True,
                 "result": {"base64": PNG_B64, "width": 7, "height": 5}}
            )
        elif method == "stale.probe":
            # A stale reply to an older call arrives first; the client
            # must skip it and match the real reply by id.
            await send({"id": 999999, "ok": True, "result": {"stale": True}})
            await send({"id": mid, "ok": True, "result": {"fresh": True}})
        else:
            await send(
                {"id": mid, "ok": False, "error": f"unknown method `{method}`"}
            )


def cfg(port: int, **kw: object) -> BridgeConfig:
    return BridgeConfig(app="gridcraft", host="127.0.0.1", port=port,
                        timeout_s=5.0, **kw)  # type: ignore[arg-type]


# --- raw client: gridcraft-style (no auth) ---


@pytest.mark.asyncio()
async def test_bridge_client_ui_inspect_wire_format() -> None:
    async with StubControlServer() as server:
        client = BridgeClient(cfg(server.port))
        await client.connect()
        try:
            result = await client.call("ui.inspect", {})
        finally:
            await client.close()
    assert result == {"tool": "select", "windows": 1, "mode": "stub"}
    # Exact wire bytes the gateway sent (compact JSON-lines, one line).
    assert json.loads(server.received[0]) == {
        "id": 1, "method": "ui.inspect", "params": {},
    }


@pytest.mark.asyncio()
async def test_bridge_client_ids_increment() -> None:
    async with StubControlServer() as server:
        client = BridgeClient(cfg(server.port))
        await client.connect()
        try:
            await client.call("ui.inspect", {})
            result = await client.call("engine.commands", {})
        finally:
            await client.close()
    assert [json.loads(line)["id"] for line in server.received] == [1, 2]
    assert result["commands"][0] == {"id": "cell.set"}


@pytest.mark.asyncio()
async def test_bridge_client_unknown_method_raises() -> None:
    async with StubControlServer() as server:
        client = BridgeClient(cfg(server.port))
        await client.connect()
        try:
            with pytest.raises(BridgeError, match="unknown method"):
                await client.call("nope.method", {})
        finally:
            await client.close()


@pytest.mark.asyncio()
async def test_bridge_client_skips_stale_lines() -> None:
    async with StubControlServer() as server:
        client = BridgeClient(cfg(server.port))
        await client.connect()
        try:
            result = await client.call("stale.probe", {})
        finally:
            await client.close()
    assert result == {"fresh": True}


@pytest.mark.asyncio()
async def test_bridge_client_call_before_connect_raises() -> None:
    client = BridgeClient(BridgeConfig(app="gridcraft", port=1, timeout_s=1.0))
    with pytest.raises(BridgeError, match="not connected"):
        await client.call("ui.inspect", {})


@pytest.mark.asyncio()
async def test_bridge_client_refuses_non_loopback() -> None:
    client = BridgeClient(
        BridgeConfig(app="gridcraft", host="192.0.2.1", port=7979, timeout_s=1.0)
    )
    with pytest.raises(BridgeError, match="loopback"):
        await client.connect()


# --- raw client: photocraft-style (auth first) ---


@pytest.mark.asyncio()
async def test_bridge_client_auth_frame_first() -> None:
    async with StubControlServer(require_token="tok-abc") as server:
        client = BridgeClient(cfg(server.port, token="tok-abc"))
        await client.connect()
        try:
            result = await client.call("ui.inspect", {})
        finally:
            await client.close()
    first = json.loads(server.received[0])
    assert first == {"id": "auth", "method": "auth",
                     "params": {"token": "tok-abc"}}
    assert result["mode"] == "stub"


@pytest.mark.asyncio()
async def test_bridge_client_auth_rejected() -> None:
    async with StubControlServer(require_token="tok-abc") as server:
        client = BridgeClient(cfg(server.port, token="wrong"))
        with pytest.raises(BridgeError, match="auth rejected"):
            await client.connect()


@pytest.mark.asyncio()
async def test_bridge_client_token_file(tmp_path) -> None:
    token_file = tmp_path / "control.token"
    token_file.write_text("tok-from-file\n", encoding="utf-8")
    async with StubControlServer(require_token="tok-from-file") as server:
        client = BridgeClient(cfg(server.port, token_file=str(token_file)))
        await client.connect()
        try:
            result = await client.call("ui.inspect", {})
        finally:
            await client.close()
    assert result["windows"] == 1


# --- screenshot metadata ---


def test_summarize_screenshot_hashes_window_pixels() -> None:
    meta = summarize_screenshot("gridcraft", {"base64": PNG_B64})
    assert meta == {
        "app": "gridcraft",
        "content_hash": f"sha256:{PNG_SHA}",
        "source": "bridge-window",
        "width": 7,
        "height": 5,
    }


def test_summarize_screenshot_without_bytes_still_diffs() -> None:
    first = summarize_screenshot("gridcraft", {"path": "a.png"})
    second = summarize_screenshot("gridcraft", {"path": "b.png"})
    assert first["source"] == "bridge-window"
    assert first["content_hash"] != second["content_hash"]


# --- bridge backend ---


@pytest.mark.asyncio()
async def test_bridge_backend_verbatim_passthrough() -> None:
    """craft_app_call {app, method, params} → TCP JSON-lines → reply."""
    async with StubControlServer() as server:
        backend = BridgeAppBackend(cfg(server.port))
        await backend.connect()
        try:
            assert "ui.inspect" in await backend.list_tools()
            result = await backend.call_tool(
                "engine.execute", {"command": "cell.set"})
        finally:
            await backend.close()
    assert result == {"ran": "cell.set"}


@pytest.mark.asyncio()
async def test_bridge_backend_render_preview_is_window_screenshot() -> None:
    async with StubControlServer() as server:
        backend = BridgeAppBackend(cfg(server.port))
        await backend.connect()
        try:
            meta = await backend.call_tool("render_preview", {"scope": "window"})
        finally:
            await backend.close()
    assert meta["source"] == "bridge-window"
    assert meta["content_hash"] == f"sha256:{PNG_SHA}"
    assert (meta["width"], meta["height"]) == (7, 5)


@pytest.mark.asyncio()
async def test_bridge_backend_doc_inspect_direct_style() -> None:
    async with StubControlServer() as server:
        backend = BridgeAppBackend(cfg(server.port, inspect_style="direct"))
        await backend.connect()
        try:
            info = await backend.call_tool("doc_inspect", {})
        finally:
            await backend.close()
    assert info["revision"] == 7
    assert info["documents"] == [{"index": 0, "path": "book.xlsx"}]


@pytest.mark.asyncio()
async def test_bridge_backend_doc_inspect_engine_style() -> None:
    async with StubControlServer() as server:
        backend = BridgeAppBackend(
            BridgeConfig(app="photocraft", host="127.0.0.1", port=server.port,
                         timeout_s=5.0, inspect_style="engine"))
        await backend.connect()
        try:
            info = await backend.call_tool("doc_inspect", {})
        finally:
            await backend.close()
    assert info["revision"] == 7


@pytest.mark.asyncio()
async def test_bridge_backend_status_reports_bridge_mode() -> None:
    async with StubControlServer() as server:
        backend = BridgeAppBackend(cfg(server.port))
        status = await backend.status()
        await backend.close()
    assert status.available is True
    assert status.running == "bridge"
    assert status.mode == "bridge"


@pytest.mark.asyncio()
async def test_bridge_backend_down_is_down_never_fake() -> None:
    backend = BridgeAppBackend(cfg(1))  # nothing listens on port 1
    status = await backend.status()
    assert status.available is False
    assert status.running == "down"
    assert status.mode == "bridge"


# --- manager + tools end to end ---


@pytest.mark.asyncio()
async def test_manager_bridge_fail_closed_on_down_app() -> None:
    manager = BackendManager(
        apps=("gridcraft",),
        bridges={"gridcraft": BridgeConfig(
            app="gridcraft", host="127.0.0.1", port=1, timeout_s=1.0)},
    )
    with pytest.raises(BackendError, match="cannot connect"):
        await manager.backend("gridcraft")
    await manager.close_all()


@pytest.mark.asyncio()
async def test_manager_bridge_backend_shared() -> None:
    async with StubControlServer() as server:
        manager = BackendManager(
            apps=("gridcraft",), bridges={"gridcraft": cfg(server.port)})
        first = await manager.backend("gridcraft")
        second = await manager.backend("gridcraft")
        assert first is second
        assert isinstance(first, BridgeAppBackend)
        assert manager.is_bridge("gridcraft") is True
        await manager.close_all()


@pytest.mark.asyncio()
async def test_craft_app_call_end_to_end() -> None:
    async with StubControlServer() as server:
        manager = BackendManager(
            apps=("gridcraft",), bridges={"gridcraft": cfg(server.port)})
        tools = Phase1Tools(manager)
        try:
            reply = await tools.craft_app_call(
                app="gridcraft", method="ui.inspect", params={})
        finally:
            await manager.close_all()
    assert reply == {"tool": "select", "windows": 1, "mode": "stub"}


@pytest.mark.asyncio()
async def test_craft_look_window_differs_from_headless() -> None:
    """Bridge craft_look returns window pixels; headless returns fake hash."""
    async with StubControlServer() as server:
        manager = BackendManager(
            apps=("gridcraft",), bridges={"gridcraft": cfg(server.port)})
        tools = Phase2Tools(manager)
        try:
            seen = await tools.craft_look(app="gridcraft", scope="window")
        finally:
            await manager.close_all()
    assert seen["source"] == "bridge-window"
    assert seen["content_hash"] == f"sha256:{PNG_SHA}"
    assert seen["content_hash"] != "sha256:fake"


@pytest.mark.asyncio()
async def test_craft_look_window_down_app_errors() -> None:
    from fastmcp.exceptions import ToolError

    manager = BackendManager(
        apps=("gridcraft",),
        bridges={"gridcraft": BridgeConfig(
            app="gridcraft", host="127.0.0.1", port=1, timeout_s=1.0)},
    )
    tools = Phase2Tools(manager)
    try:
        with pytest.raises(ToolError):
            await tools.craft_look(app="gridcraft", scope="window")
    finally:
        await manager.close_all()


# --- env config + wire transcript ---


def test_bridges_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRAFTER_BRIDGE_GRIDCRAFT", "127.0.0.1:7979")
    monkeypatch.setenv("CRAFTER_BRIDGE_GRIDCRAFT_TOKEN_FILE", "/tmp/g.token")
    configs = bridges_from_env(("gridcraft",))
    assert configs["gridcraft"].port == 7979
    assert configs["gridcraft"].token_file == "/tmp/g.token"
    assert configs["gridcraft"].inspect_style == "direct"


def test_bridges_from_env_bad_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRAFTER_BRIDGE_GRIDCRAFT", "not-a-port")
    with pytest.raises(BridgeError, match="host:port"):
        bridges_from_env(("gridcraft",))


@pytest.mark.asyncio()
async def test_wire_transcript_exact_bytes() -> None:
    """Pin the exact wire format (source for the runbook transcript)."""
    async with StubControlServer(require_token="tok-abc") as server:
        client = BridgeClient(cfg(server.port, token="tok-abc"))
        await client.connect()
        try:
            await client.call("ui.inspect", {})
        finally:
            await client.close()
    assert server.received[0] == (
        '{"id":"auth","method":"auth","params":{"token":"tok-abc"}}'
    )
    assert server.received[1] == '{"id":1,"method":"ui.inspect","params":{}}'


async def _big_line_server(payload_len: int) -> asyncio.Server:
    """Raw control server answering one call with a huge result line."""

    async def handle(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        raw = await reader.readline()
        msg = json.loads(raw.decode("utf-8"))
        blob = "x" * payload_len
        writer.write(
            (
                json.dumps({"id": msg.get("id"), "ok": True, "result": {"blob": blob}})
                + "\n"
            ).encode("utf-8")
        )
        await writer.drain()
        writer.close()

    return await asyncio.start_server(handle, "127.0.0.1", 0)


@pytest.mark.asyncio()
async def test_bridge_client_accepts_reply_above_64k() -> None:
    """Regression: the default 64 KiB StreamReader cap used to kill every
    screenshot-sized reply with a raw ValueError (live 500)."""
    server = await _big_line_server(200 * 1024)
    async with server:
        port = server.sockets[0].getsockname()[1]
        client = BridgeClient(cfg(port))
        await client.connect()
        try:
            result = await client.call("ui.inspect", {})
        finally:
            await client.close()
    assert len(result["blob"]) == 200 * 1024


@pytest.mark.asyncio()
async def test_bridge_client_oversized_reply_is_bridge_error() -> None:
    """Past the 8 MiB desktop ceiling the failure is an honest
    BridgeError (callers map it to 502), never a raw ValueError."""
    server = await _big_line_server(9 * 1024 * 1024)
    async with server:
        port = server.sockets[0].getsockname()[1]
        client = BridgeClient(cfg(port))
        await client.connect()
        try:
            with pytest.raises(BridgeError, match="8 MiB"):
                await client.call("ui.inspect", {})
        finally:
            await client.close()
