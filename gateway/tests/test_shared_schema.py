"""Shared live-agent tool schema parity (chat agent ↔ external MCP clients).

Positive: ``craft_run_tool`` accepts the shared schema names (``command_run``,
``command_list``, ``doc_inspect``, ``doc_save``, ``look``) and forwards each
to the app backend with name and args unchanged — the same call the app MCP
``tools/call`` receives (``AppBackend.call_tool`` forwards any tool name
verbatim; ``command_run`` then runs ``engine.execute {command, params}`` per
the shared schema). Negative: ``doc_save`` paths escaping the session write
root (``..``, absolute outside) are refused before the backend sees them.
Schema table: docs/bridge-runbook.md §7; method semantics: photocraft
docs/control-protocol.md §MCP bridge.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp.exceptions import ToolError

from gateway.backends import FakeAppBackend, SessionRegistry
from gateway.tools_phase1 import Phase1Tools

SHARED_CALLS = (
    ("command_run", {"command": "image.imageRotation.90cw", "params": {}}),
    ("command_list", {"filter": "image"}),
    ("doc_inspect", {}),
    ("doc_save", {"path": "out.pcraft"}),
    ("look", {}),
)


class RecordingAppBackend(FakeAppBackend):
    """Fake backend that records every ``(method, params)`` it is offered."""

    def __init__(self, app: str) -> None:
        super().__init__(app)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((method, dict(params)))
        return await super().call_tool(method, params)


class StubBackendManager:
    """Minimal manager stand-in (Phase1Tools needs only ``backend()``)."""

    def __init__(self, backend: RecordingAppBackend) -> None:
        self._backend = backend

    async def backend(self, app: str) -> RecordingAppBackend:
        return self._backend


@pytest.fixture()
def setup(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    backend = RecordingAppBackend("photocraft")
    sessions = SessionRegistry(default_roots=[work])
    sessions.create("s1", "alice")
    impl = Phase1Tools(StubBackendManager(backend), sessions)
    return impl, backend, work


@pytest.mark.asyncio()
async def test_craft_run_tool_forwards_shared_schema_names(setup) -> None:
    impl, backend, work = setup
    results = {}
    for tool, args in SHARED_CALLS:
        results[tool] = await impl.craft_run_tool(
            app="photocraft", tool=tool, args=args, user_id="alice", session_id="s1"
        )
    # Names and arg shapes reach the backend verbatim; doc_save's path is
    # confined to the session write root on the way through.
    assert backend.calls == [
        ("command_run", {"command": "image.imageRotation.90cw", "params": {}}),
        ("command_list", {"filter": "image"}),
        ("doc_inspect", {}),
        ("doc_save", {"path": str(work / "out.pcraft")}),
        ("look", {}),
    ]
    # command_run answers with the engine.execute canned shape (shared
    # schema mapping); look with the render_preview one.
    assert results["command_run"] == {
        "app": "photocraft",
        "ok": True,
        "revision": 2,
    }
    assert results["look"]["content_hash"] == "sha256:fake"
    assert results["doc_save"]["path"] == str(work / "out.pcraft")
    # doc_save escapes are refused before the app sees any bytes.
    for evil in ("../escape.pcraft", "/etc/passwd"):
        with pytest.raises(ToolError, match="access denied"):
            await impl.craft_run_tool(
                app="photocraft",
                tool="doc_save",
                args={"path": evil},
                user_id="alice",
                session_id="s1",
            )
    assert len(backend.calls) == len(SHARED_CALLS)
