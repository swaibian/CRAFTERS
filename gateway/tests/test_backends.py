"""SWE4 unit tests for gateway/backends.py (SWE3-A-01).

Positive: fake backend status/call/list_tools; session create/get/drop;
in-roots path checks; BackendManager shares backends across sessions.
Negative: unknown session; path escape (.., absolute outside roots, sibling
prefix); unknown app; unknown backend method; no roots configured.
"""

from __future__ import annotations

import pytest

from gateway.backends import (
    AppBackend,
    BackendError,
    BackendManager,
    FakeAppBackend,
    RootsViolation,
    SessionRegistry,
)


@pytest.fixture()
def registry(tmp_path) -> SessionRegistry:
    work = tmp_path / "work"
    work.mkdir()
    return SessionRegistry(default_roots=[work])


# --- sessions ---


def test_session_create_get_drop(registry: SessionRegistry) -> None:
    session = registry.create("s1", "alice", key_id="key_alice")
    assert registry.get("s1") is session
    assert session.user_id == "alice"
    assert registry.drop("s1") is True
    assert registry.get("s1") is None
    assert registry.drop("s1") is False


def test_check_path_allows_inside_roots(registry: SessionRegistry, tmp_path) -> None:
    registry.create("s1", "alice")
    resolved = registry.check_path("s1", "doc.txt")
    assert str(resolved).startswith(str(tmp_path / "work"))


def test_check_path_unknown_session(registry: SessionRegistry) -> None:
    with pytest.raises(RootsViolation, match="unknown session"):
        registry.check_path("nope", "doc.txt")


def test_check_path_no_roots_configured() -> None:
    empty = SessionRegistry()
    empty.create("s1", "alice")
    with pytest.raises(RootsViolation, match="no roots"):
        empty.check_path("s1", "doc.txt")


@pytest.mark.parametrize(
    "evil",
    [
        "../escape.txt",
        "../../etc/passwd",
        "/etc/passwd",
        "/tmp/work-evil/doc.txt",  # sibling-prefix trick
    ],
)
def test_check_path_rejects_escape(
    registry: SessionRegistry, tmp_path, evil: str
) -> None:
    registry.create("s1", "alice")
    with pytest.raises(RootsViolation):
        registry.check_path("s1", evil)


def test_check_path_second_root_allowed(tmp_path) -> None:
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()
    registry = SessionRegistry()
    registry.create("s1", "alice", roots=[first, second])
    resolved = registry.check_path("s1", str(second / "a.txt"))
    assert resolved == second / "a.txt"


def test_sessions_isolated(registry: SessionRegistry, tmp_path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    registry.create("s1", "alice")
    registry.create("s2", "bob", roots=[other])
    # s1 cannot reach s2's root.
    with pytest.raises(RootsViolation):
        registry.check_path("s1", str(other / "x.txt"))
    # s2 cannot reach s1's default root.
    with pytest.raises(RootsViolation):
        registry.check_path("s2", str(tmp_path / "work" / "x.txt"))


# --- fake backend ---


@pytest.mark.asyncio()
async def test_fake_backend_status() -> None:
    backend = FakeAppBackend("photocraft")
    status = await backend.status()
    assert status.app == "photocraft"
    assert status.available is True
    assert status.documents and status.jobs == []


@pytest.mark.asyncio()
async def test_fake_backend_call_tool() -> None:
    backend = FakeAppBackend("pdfcraft")
    info = await backend.call_tool("doc_inspect", {})
    assert info["app"] == "pdfcraft"
    assert info["revision"] == 1
    executed = await backend.call_tool("engine.execute", {"command": "noop"})
    assert executed["ok"] is True
    assert executed["revision"] == 2


@pytest.mark.asyncio()
async def test_fake_backend_unknown_method() -> None:
    backend = FakeAppBackend("gridcraft")
    with pytest.raises(BackendError, match="unknown method"):
        await backend.call_tool("nope", {})


@pytest.mark.asyncio()
async def test_fake_backend_list_tools() -> None:
    backend = FakeAppBackend("gridcraft")
    assert "doc_inspect" in await backend.list_tools()


# --- manager ---


@pytest.mark.asyncio()
async def test_manager_fake_backend_shared_across_sessions(tmp_path) -> None:
    manager = BackendManager(use_fake=True)
    first = await manager.backend("photocraft")
    second = await manager.backend("photocraft")
    assert first is second  # shared process, isolation lives in roots
    assert isinstance(first, FakeAppBackend)
    await manager.close_all()


@pytest.mark.asyncio()
async def test_manager_unknown_app() -> None:
    manager = BackendManager(use_fake=True)
    with pytest.raises(BackendError, match="unknown app"):
        await manager.backend("nosuchcraft")
    await manager.close_all()


@pytest.mark.asyncio()
async def test_manager_loud_fake_fallback_when_no_cli_present(caplog) -> None:
    """Inverted fallback: real is default; missing binary falls back LOUD.

    ``use_fake`` stays False (fake was never opted in); the per-app fake
    carries ``mode == "fake"`` so ``craft_status`` exposes it, and a
    WARNING is logged.
    """
    import logging

    manager = BackendManager(apps=("definitelynotacli",), use_fake=False)
    assert manager.use_fake is False
    with caplog.at_level(logging.WARNING, logger="gateway"):
        backend = await manager.backend("definitelynotacli")
    assert isinstance(backend, FakeAppBackend)
    assert manager.is_fake("definitelynotacli") is True
    assert "definitelynotacli" in manager.fake_fallback_apps
    status = await backend.status()
    assert status.mode == "fake"
    assert any(
        "backend_fake_fallback" in record.getMessage() for record in caplog.records
    )
    await manager.close_all()


@pytest.mark.asyncio()
async def test_manager_explicit_fake_opt_in() -> None:
    """``use_fake=True`` forces fakes without any fallback bookkeeping."""
    manager = BackendManager(apps=("definitelynotacli",), use_fake=True)
    assert manager.use_fake is True
    backend = await manager.backend("definitelynotacli")
    assert isinstance(backend, FakeAppBackend)
    assert manager.fake_fallback_apps == frozenset()
    await manager.close_all()


def test_load_cli_paths_missing_file_degrades_gracefully(tmp_path) -> None:
    """Missing sync file → {} (PATH lookup applies), never an error."""
    from gateway.backends import load_cli_paths

    paths = load_cli_paths(env_file=tmp_path / "does-not-exist.env", env={})
    assert paths == {}


def test_load_cli_paths_precedence(tmp_path) -> None:
    """Sync file < CRAFTER_CLI_PATHS < per-app env vars."""
    from gateway.backends import load_cli_paths

    sync = tmp_path / "bin-paths.env"
    sync.write_text("PHOTOCRAFT_CLI=/sync/photo\nPDFCRAFT_CLI=/sync/pdf\n")
    paths = load_cli_paths(
        env_file=sync,
        env={
            "CRAFTER_CLI_PATHS": "PDFCRAFT_CLI=/override/pdf",
            "GRIDCRAFT_CLI": "/env/grid",
        },
    )
    assert paths["PHOTOCRAFT_CLI"] == "/sync/photo"
    assert paths["PDFCRAFT_CLI"] == "/override/pdf"
    assert paths["GRIDCRAFT_CLI"] == "/env/grid"


def test_resolve_cli_command_prefers_explicit_executable(tmp_path) -> None:
    """Explicit executable path wins over PATH."""
    from gateway.backends import resolve_cli_command

    fake_bin = tmp_path / "photocraft-cli"
    fake_bin.write_text("#!/bin/sh\n")
    fake_bin.chmod(0o755)
    argv = resolve_cli_command(
        "photocraft", {"PHOTOCRAFT_CLI": str(fake_bin)}
    )
    assert argv == [str(fake_bin), "mcp"]


def test_resolve_cli_command_dead_path_falls_through(tmp_path) -> None:
    """Configured-but-missing path degrades to PATH lookup (None here)."""
    from gateway.backends import resolve_cli_command

    assert (
        resolve_cli_command(
            "definitelynotacli",
            {"DEFINITELLYNOTACLI_CLI": str(tmp_path / "nope")},
        )
        is None
    )
    assert resolve_cli_command("definitelynotacli", {}) is None


@pytest.mark.asyncio()
async def test_real_backend_missing_cli_reports_down() -> None:
    backend = AppBackend("definitelynotacli")
    status = await backend.status()
    assert status.available is False
    assert status.running == "down"
    assert status.last_error is not None
    await backend.close()
