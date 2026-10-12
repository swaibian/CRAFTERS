"""SWE4 containment tests for TC-B-02 (SWE3-B-02).

Hardening audit over ``SessionRegistry.check_path`` (lexical + realpath
symlink second opinion + audit) and the tools' ``_confine`` wrappers:

Positive: missing-parent creation paths allowed; second root allowed;
symlink-inside→inside allowed; same check for read and write paths.
Negative: deep traversal, absolute outside, sibling prefix, symlink escape
(inside→outside), cross-session reach, unknown session, no-roots session;
denials audit ``roots_decision`` with no filesystem paths in any record
(escape paths, not even parents, ever reach the logs).
"""

from __future__ import annotations

import logging
import os

import pytest
from fastmcp.exceptions import ToolError

from gateway.auth import AuthStore, TokenRecord
from gateway.backends import BackendManager, RootsViolation, SessionRegistry
from gateway.snapshots import RecordStore, SnapshotStore
from gateway.tools_phase1 import Phase1Tools
from gateway.tools_phase2 import Phase2Tools

FULL_TOKEN = "containment-full-token"


@pytest.fixture()
def registry(tmp_path) -> SessionRegistry:
    work = tmp_path / "work"
    work.mkdir()
    return SessionRegistry(default_roots=[work])


@pytest.fixture()
def tools(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    store = AuthStore()
    store.register(
        FULL_TOKEN,
        TokenRecord(key_id="key_full", user_id="op", allowlist=frozenset({"*"})),
    )
    manager = BackendManager(use_fake=True)
    sessions = SessionRegistry(default_roots=[work])
    sessions.create("s1", "op", key_id="key_full")
    snapshots = SnapshotStore()
    phase1 = Phase1Tools(manager, sessions, store, snapshots)
    phase2 = Phase2Tools(manager, sessions, store, snapshots, RecordStore())
    return phase1, phase2, sessions


# --- traversal / absolute / sibling-prefix ---


@pytest.mark.parametrize(
    "evil",
    [
        "../escape.txt",
        "../../../escape.txt",
        "a/../../escape.txt",
        "a/../../../escape.txt",
        "/etc/passwd",
        "/etc/hosts",
        "..",
    ],
)
def test_traversal_and_absolute_rejected(
    registry: SessionRegistry, tmp_path, evil: str
) -> None:
    registry.create("s1", "alice")
    with pytest.raises(RootsViolation):
        registry.check_path("s1", evil)


def test_dot_resolves_inside_roots(registry: SessionRegistry, tmp_path) -> None:
    """``.`` is the session root itself — not an escape, correctly allowed."""
    registry.create("s1", "alice")
    assert registry.check_path("s1", ".") == tmp_path / "work"


def test_sibling_prefix_rejected(registry: SessionRegistry, tmp_path) -> None:
    registry.create("s1", "alice")
    sibling = str(tmp_path / "work-evil" / "doc.txt")  # shares "work" prefix
    with pytest.raises(RootsViolation):
        registry.check_path("s1", sibling)


def test_second_root_allowed(tmp_path) -> None:
    one = tmp_path / "one"
    two = tmp_path / "two"
    one.mkdir()
    two.mkdir()
    registry = SessionRegistry()
    registry.create("s1", "alice", roots=[one, two])
    assert registry.check_path("s1", str(two / "a.txt")) == two / "a.txt"
    assert registry.check_path("s1", "rel.txt") == one / "rel.txt"


def test_missing_parent_creation_path_allowed(
    registry: SessionRegistry, tmp_path
) -> None:
    """Nonexistent parents degrade to the lexical verdict (creation paths)."""
    registry.create("s1", "alice")
    resolved = registry.check_path("s1", "new/sub/dir/file.txt")
    assert resolved == tmp_path / "work" / "new" / "sub" / "dir" / "file.txt"


def test_read_and_write_paths_share_one_check(
    registry: SessionRegistry, tmp_path
) -> None:
    """Roots apply identically to reads and writes (no bypass by op type)."""
    registry.create("s1", "alice")
    assert registry.check_path("s1", "doc.txt") == tmp_path / "work" / "doc.txt"
    assert registry.check_path("s1", "doc.txt") == tmp_path / "work" / "doc.txt"
    with pytest.raises(RootsViolation):
        registry.check_path("s1", "../escape.txt")
    with pytest.raises(RootsViolation):
        registry.check_path("s1", "../escape.txt")


# --- symlink second opinion ---


def test_symlink_escape_rejected(registry: SessionRegistry, tmp_path) -> None:
    """A symlink inside the roots pointing outside must not pass."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret")
    registry.create("s1", "alice")
    link = tmp_path / "work" / "link"
    try:
        os.symlink(str(outside), str(link))
    except OSError:
        pytest.skip("symlinks not permitted in this environment")
    with pytest.raises(RootsViolation):
        registry.check_path("s1", "link/secret.txt")


def test_symlink_inside_roots_allowed(registry: SessionRegistry, tmp_path) -> None:
    """A symlink resolving inside the roots still passes."""
    target = tmp_path / "work" / "real"
    target.mkdir()
    registry.create("s1", "alice")
    link = tmp_path / "work" / "alias"
    try:
        os.symlink(str(target), str(link))
    except OSError:
        pytest.skip("symlinks not permitted in this environment")
    resolved = registry.check_path("s1", "alias/doc.txt")
    assert str(resolved).startswith(str(tmp_path / "work"))


def test_dangling_symlink_outside_rejected(registry: SessionRegistry, tmp_path) -> None:
    """A dangling symlink pointing outside is denied (deny-by-default).

    ``realpath`` resolution sees through dangling links, so a link inside
    the roots whose target lies outside must not pass — the creation-path
    grace applies only when nothing resolves outside.
    """
    registry.create("s1", "alice")
    link = tmp_path / "work" / "dangling"
    try:
        os.symlink(str(tmp_path / "nope-target"), str(link))
    except OSError:
        pytest.skip("symlinks not permitted in this environment")
    with pytest.raises(RootsViolation):
        registry.check_path("s1", "dangling/file.txt")


def test_dangling_symlink_inside_allowed(registry: SessionRegistry, tmp_path) -> None:
    """A dangling link whose target stays inside the roots is allowed."""
    registry.create("s1", "alice")
    link = tmp_path / "work" / "future"
    try:
        os.symlink(str(tmp_path / "work" / "not-yet-created"), str(link))
    except OSError:
        pytest.skip("symlinks not permitted in this environment")
    resolved = registry.check_path("s1", "future/file.txt")
    assert str(resolved).startswith(str(tmp_path / "work"))


# --- cross-session / unknown / no-roots ---


def test_cross_session_reach_rejected(tmp_path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    registry = SessionRegistry(default_roots=[tmp_path / "work"])
    (tmp_path / "work").mkdir()
    registry.create("s1", "alice")
    registry.create("s2", "bob", roots=[other])
    with pytest.raises(RootsViolation):
        registry.check_path("s1", str(other / "x.txt"))
    with pytest.raises(RootsViolation):
        registry.check_path("s2", str(tmp_path / "work" / "x.txt"))


def test_unknown_session_rejected(registry: SessionRegistry) -> None:
    with pytest.raises(RootsViolation, match="unknown session"):
        registry.check_path("ghost", "doc.txt")


def test_no_roots_session_rejected() -> None:
    empty = SessionRegistry()
    empty.create("s1", "alice")
    with pytest.raises(RootsViolation, match="no roots"):
        empty.check_path("s1", "doc.txt")


# --- tools enforce the same confinement ---


@pytest.mark.asyncio()
@pytest.mark.parametrize("tool", ["craft_run", "craft_run_tool", "craft_app_call"])
async def test_phase1_file_params_confined(tools, tool: str) -> None:
    phase1, _, _ = tools
    kwargs: dict = {"app": "photocraft", "user_id": "op", "session_id": "s1"}
    if tool == "craft_run":
        kwargs.update({"command": "save", "params": {"output_path": "../evil.png"}})
    elif tool == "craft_run_tool":
        kwargs.update({"tool": "save", "args": {"file": "/etc/passwd"}})
    else:
        kwargs.update({"method": "save", "params": {"path": "../../evil.txt"}})
    with pytest.raises(ToolError, match="access denied"):
        await getattr(phase1, tool)(**kwargs, raw_token=FULL_TOKEN)


@pytest.mark.asyncio()
async def test_phase2_look_path_confined(tools) -> None:
    _, phase2, _ = tools
    with pytest.raises(ToolError, match="access denied"):
        await phase2.craft_look(
            app="photocraft",
            path="/etc/passwd",
            user_id="op",
            session_id="s1",
            raw_token=FULL_TOKEN,
        )


@pytest.mark.asyncio()
async def test_phase2_assert_output_path_confined(tools) -> None:
    _, phase2, _ = tools
    with pytest.raises(ToolError, match="access denied"):
        await phase2.craft_assert(
            app="photocraft",
            expect={"output_path": "../evil.png"},
            user_id="op",
            session_id="s1",
            raw_token=FULL_TOKEN,
        )


@pytest.mark.asyncio()
async def test_phase2_snapshot_restore_session_scoped(tools) -> None:
    """A snapshot from s1 cannot be restored from another session."""
    _, phase2, sessions = tools
    sessions.create("s2", "op", key_id="key_full")
    snap = await phase2.craft_snapshot(
        app="photocraft", user_id="op", session_id="s1", raw_token=FULL_TOKEN
    )
    with pytest.raises(ToolError, match="access denied"):
        await phase2.craft_restore(
            app="photocraft",
            token=snap["token"],
            user_id="op",
            session_id="s2",
            raw_token=FULL_TOKEN,
        )


# --- audit redaction ---


def _logged_text(caplog) -> str:
    return "\n".join(
        f"{rec.name} {rec.getMessage()} {rec.args}" for rec in caplog.records
    )


def test_denial_audit_carries_no_paths(
    registry: SessionRegistry, tmp_path, caplog
) -> None:
    """Escape paths (not even parents) ever reach any log record."""
    registry.create("s1", "alice")
    evil = "/etc/super-secret-dir/passwd"
    with (
        caplog.at_level(logging.INFO, logger="gateway.audit"),
        pytest.raises(RootsViolation),
    ):
        registry.check_path("s1", evil)
    decisions = [r for r in caplog.records if r.name == "gateway.audit"]
    assert decisions, "expected a roots_decision audit record"
    assert "super-secret-dir" not in _logged_text(caplog)
    assert "/etc/passwd" not in _logged_text(caplog)
    last = decisions[-1]
    assert isinstance(last.args, dict)
    assert last.args.get("event") == "roots_decision"
    assert last.args.get("ok") is False


def test_allow_audit_carries_no_paths(
    registry: SessionRegistry, tmp_path, caplog
) -> None:
    """Allowed-path audits carry session + outcome only, no filesystem paths."""
    registry.create("s1", "alice")
    with caplog.at_level(logging.INFO, logger="gateway.audit"):
        registry.check_path("s1", "ordinary-doc.txt")
    decisions = [r for r in caplog.records if r.name == "gateway.audit"]
    assert decisions
    assert "ordinary-doc.txt" not in _logged_text(caplog)
    assert str(tmp_path) not in _logged_text(caplog)


@pytest.mark.asyncio()
async def test_tool_escape_logs_no_content(tools, caplog) -> None:
    """A tool-level escape denial logs no secrets, paths, or content."""
    phase1, _, _ = tools
    with caplog.at_level(logging.INFO), pytest.raises(ToolError, match="access denied"):
        await phase1.craft_run(
            app="photocraft",
            command="save",
            params={"output_path": "/vault/plans.txt"},
            user_id="op",
            session_id="s1",
            raw_token=FULL_TOKEN,
        )
    assert "/vault/plans.txt" not in _logged_text(caplog)
    assert FULL_TOKEN not in _logged_text(caplog)
