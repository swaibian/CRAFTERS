"""Real-backend tests: AppBackend against live ``<app>-cli mcp`` (Lane 2).

Every test here spawns a REAL pilot CLI subprocess — no fakes. Binaries
resolve via the Lane 1 sync file ``deploy/local-bin-paths.env`` → env
overrides → ``PATH`` (see ``gateway.backends.load_cli_paths``).

Run only when pilot CLIs are installed::

    python3 -m pytest gateway/tests/test_backends_real.py -q

CI without binaries skips the whole module::

    python3 -m pytest gateway/tests/ -q -m "not real"

A missing binary is a SKIP (Lane 1 not landed yet), never a failure.
Anything that connects but misbehaves is a real FAILURE.
"""

from __future__ import annotations

import pytest

from gateway.backends import (
    PILOT_APPS,
    AppBackend,
    BackendManager,
    FakeAppBackend,
    load_cli_paths,
    resolve_cli_command,
)

pytestmark = pytest.mark.real


def _require_binary(app: str) -> None:
    """Skip the test when ``app`` has no usable CLI binary yet."""
    if resolve_cli_command(app) is None:
        paths = load_cli_paths()
        pytest.skip(
            f"no {app}-cli binary (Lane 1 not landed; "
            f"sync file holds {sorted(paths) or 'nothing yet'})"
        )


@pytest.mark.asyncio()
@pytest.mark.parametrize("app", PILOT_APPS)
async def test_real_backend_list_tools(app: str) -> None:
    """Spawn ``<app>-cli mcp`` and list its tools (must be a real AppBackend)."""
    _require_binary(app)
    backend = AppBackend(app)
    await backend.connect()
    try:
        assert isinstance(backend, AppBackend)
        assert not isinstance(backend, FakeAppBackend)
        tools = await backend.list_tools()
        assert isinstance(tools, list) and tools, "real CLI exposed no tools"
    finally:
        await backend.close()


@pytest.mark.asyncio()
@pytest.mark.parametrize("app", PILOT_APPS)
async def test_real_backend_read_only_inspect(app: str) -> None:
    """One harmless read-only call per app; response must not be canned-fake."""
    _require_binary(app)
    backend = AppBackend(app)
    await backend.connect()
    try:
        tools = await backend.list_tools()
        # Prefer the read-only inspectors; fall back to the first
        # list/inspect-sounding tool so new CLI contracts don't break us.
        candidates = ["doc_inspect", "command_list"] + [
            t for t in tools if "inspect" in t or "list" in t
        ]
        errors: list[str] = []
        for method in candidates:
            if method not in tools:
                continue
            try:
                result = await backend.call_tool(method, {})
            except Exception as exc:  # noqa: BLE001 — try next candidate
                errors.append(f"{method}: {exc}")
                continue
            assert isinstance(result, dict), f"{method} returned non-dict"
            assert "sha256:fake" not in str(result), f"{method} smells canned-fake"
            return
        pytest.fail(f"no read-only tool answered on {app}: {errors or tools}")
    finally:
        await backend.close()


@pytest.mark.asyncio()
@pytest.mark.parametrize("app", PILOT_APPS)
async def test_real_backend_status_mode(app: str) -> None:
    """Real status must be available with a non-fake mode."""
    _require_binary(app)
    manager = BackendManager(apps=(app,), use_fake=False)
    try:
        backend = await manager.backend(app)
        assert isinstance(backend, AppBackend)
        assert manager.is_fake(app) is False
        status = await backend.status()
        assert status.available is True
        assert status.mode != "fake", "real backend reported fake mode"
        assert status.mode == "headless"
    finally:
        await manager.close_all()
