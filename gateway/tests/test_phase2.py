"""SWE4 unit tests for gateway/tools_phase2.py + gateway/snapshots.py (SWE3-B-01).

Positive: look scopes/details; snapshot/restore round-trip; record with
evidence; structural + visual asserts; auto-snapshot hook on destructive
craft_run; full register_phase2_tools wiring.
Negative: unbacked measured claims; unknown app/scope/assertion; visual
assert without tolerance; cross-session/app restore; roots escape on
look/assert paths; allowlist denial; no token/content/image data in logs.
"""

from __future__ import annotations

import logging

import pytest
from fastmcp.exceptions import ToolError

from gateway.auth import AuthStore, TokenRecord
from gateway.backends import BackendManager, SessionRegistry
from gateway.snapshots import (
    RecordStore,
    SnapshotError,
    SnapshotStore,
    is_destructive_command,
)
from gateway.tools_phase1 import Phase1Tools
from gateway.tools_phase2 import (
    TOOL_NAMES,
    Phase2Tools,
    register_phase2_tools,
)

ALICE_TOKEN = "alice-phase2-token"
BOGUS_TOKEN = "bogus-token"


@pytest.fixture()
def setup(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    store = AuthStore()
    store.register(
        ALICE_TOKEN,
        TokenRecord(
            key_id="key_alice",
            user_id="alice",
            allowlist=frozenset(
                {
                    "craft_look",
                    "craft_snapshot",
                    "craft_restore",
                    "craft_record",
                    "craft_assert",
                    "craft_run",
                }
            ),
        ),
    )
    manager = BackendManager(use_fake=True)
    sessions = SessionRegistry(default_roots=[work])
    sessions.create("s1", "alice", key_id="key_alice")
    sessions.create("s2", "alice", key_id="key_alice")
    snapshots = SnapshotStore()
    records = RecordStore()
    impl = Phase2Tools(manager, sessions, store, snapshots, records)
    phase1 = Phase1Tools(manager, sessions, store, snapshots)
    return impl, phase1, manager, sessions, store, snapshots, records


def test_tool_names_complete() -> None:
    assert set(TOOL_NAMES) == {
        "craft_look",
        "craft_snapshot",
        "craft_restore",
        "craft_record",
        "craft_assert",
    }


# --- craft_look ---


@pytest.mark.asyncio()
@pytest.mark.parametrize(
    "scope", ["content", "window", "region", "outline", "contact_sheet"]
)
async def test_look_scopes(setup, scope: str) -> None:
    impl, *_ = setup
    result = await impl.craft_look(
        app="photocraft", scope=scope, user_id="alice", session_id="s1"
    )
    assert result["app"] == "photocraft"
    assert result["scope"] == scope
    assert result["content_hash"] == "sha256:fake"
    assert "revision" in result


@pytest.mark.asyncio()
@pytest.mark.parametrize("detail", ["thumbnail", "normal", "full"])
async def test_look_details(setup, detail: str) -> None:
    impl, *_ = setup
    result = await impl.craft_look(
        app="pdfcraft", detail=detail, user_id="alice", session_id="s1"
    )
    assert result["detail"] == detail


@pytest.mark.asyncio()
async def test_look_region_and_clamp(setup) -> None:
    impl, *_ = setup
    result = await impl.craft_look(
        app="photocraft",
        scope="region",
        region=[0, 0, 100, 100],
        max_side=99999,
        user_id="alice",
        session_id="s1",
    )
    assert result["scope"] == "region"


@pytest.mark.asyncio()
async def test_look_rejects_bad_scope_detail_region(setup) -> None:
    impl, *_ = setup
    with pytest.raises(ToolError, match="unknown scope"):
        await impl.craft_look(
            app="photocraft", scope="xray", user_id="alice", session_id="s1"
        )
    with pytest.raises(ToolError, match="unknown detail"):
        await impl.craft_look(
            app="photocraft", detail="ultra", user_id="alice", session_id="s1"
        )
    with pytest.raises(ToolError, match="region must be"):
        await impl.craft_look(
            app="photocraft", region=[0, 0], user_id="alice", session_id="s1"
        )
    with pytest.raises(ToolError, match="unknown app"):
        await impl.craft_look(app="nosuchcraft", user_id="alice", session_id="s1")


@pytest.mark.asyncio()
async def test_look_path_roots_escape_denied(setup) -> None:
    impl, *_ = setup
    ok = await impl.craft_look(
        app="photocraft", path="render.png", user_id="alice", session_id="s1"
    )
    assert ok["app"] == "photocraft"
    with pytest.raises(ToolError, match="access denied"):
        await impl.craft_look(
            app="photocraft",
            path="../../escape.png",
            user_id="alice",
            session_id="s1",
        )


# --- snapshot / restore ---


@pytest.mark.asyncio()
async def test_snapshot_restore_round_trip(setup) -> None:
    """Acceptance 2 (unit half): snapshot → edit → restore returns prior rev."""
    impl, phase1, *_ = setup
    snap = await impl.craft_snapshot(
        app="photocraft", label="before", user_id="alice", session_id="s1"
    )
    assert snap["revision"] == 1
    assert snap["token"].startswith("snap_")
    edited = await phase1.craft_run(
        app="photocraft",
        command="filter.blur",
        params={"radius": 2},
        user_id="alice",
        session_id="s1",
    )
    assert edited["revision"] == 2
    restored = await impl.craft_restore(
        app="photocraft", token=snap["token"], user_id="alice", session_id="s1"
    )
    assert restored == {"restored_to": 1, "app": "photocraft"}


@pytest.mark.asyncio()
async def test_restore_rejects_unknown_cross_session_cross_app(setup) -> None:
    impl, *_ = setup
    snap = await impl.craft_snapshot(app="photocraft", user_id="alice", session_id="s1")
    with pytest.raises(ToolError, match="unknown snapshot"):
        await impl.craft_restore(
            app="photocraft", token="snap_nope", user_id="alice", session_id="s1"
        )
    with pytest.raises(ToolError, match="access denied"):
        await impl.craft_restore(
            app="photocraft",
            token=snap["token"],
            user_id="alice",
            session_id="s2",
        )
    with pytest.raises(ToolError, match="app mismatch"):
        await impl.craft_restore(
            app="pdfcraft", token=snap["token"], user_id="alice", session_id="s1"
        )


def test_snapshot_store_session_isolation_and_drop() -> None:
    store = SnapshotStore()
    first = store.create(session_id="s1", app="a", revision=1)
    store.create(session_id="s2", app="a", revision=5)
    assert [r.token for r in store.list_for_session("s1")] == [first.token]
    with pytest.raises(SnapshotError):
        store.restore(first.token, "s2")
    assert store.drop_session("s1") == 1
    assert store.list_for_session("s1") == []
    with pytest.raises(SnapshotError):
        store.restore(first.token, "s1")


# --- craft_record ---


@pytest.mark.asyncio()
async def test_record_measured_with_evidence_ok(setup) -> None:
    impl, *_ = setup
    result = await impl.craft_record(
        claim="blur applied",
        confidence="measured",
        evidence=[{"kind": "assert", "id": "a1", "revision": 2}],
        user_id="alice",
        session_id="s1",
    )
    assert result["confidence"] == "measured"
    assert result["evidence_count"] == 1
    assert result["record_id"].startswith("rec_")


@pytest.mark.asyncio()
async def test_record_rejects_unbacked_measured_claim(setup) -> None:
    """Acceptance 1: measured + empty evidence is rejected."""
    impl, *_ = setup
    with pytest.raises(ToolError, match="require evidence"):
        await impl.craft_record(
            claim="blur applied",
            confidence="measured",
            evidence=[],
            user_id="alice",
            session_id="s1",
        )
    with pytest.raises(ToolError, match="require evidence"):
        await impl.craft_record(
            claim="blur applied",
            confidence="measured",
            user_id="alice",
            session_id="s1",
        )


@pytest.mark.asyncio()
async def test_record_inferred_without_evidence_ok(setup) -> None:
    impl, *_ = setup
    result = await impl.craft_record(
        claim="looks plausible",
        confidence="inferred",
        user_id="alice",
        session_id="s1",
    )
    assert result["evidence_count"] == 0


@pytest.mark.asyncio()
async def test_record_rejects_bad_claim_confidence_evidence(setup) -> None:
    impl, *_ = setup
    with pytest.raises(ToolError, match="non-empty"):
        await impl.craft_record(
            claim="  ", confidence="inferred", user_id="alice", session_id="s1"
        )
    with pytest.raises(ToolError, match="unknown confidence"):
        await impl.craft_record(
            claim="x", confidence="guessed", user_id="alice", session_id="s1"
        )
    with pytest.raises(ToolError, match="unknown evidence kind"):
        await impl.craft_record(
            claim="x",
            confidence="inferred",
            evidence=[{"kind": "vibes", "id": "1"}],
            user_id="alice",
            session_id="s1",
        )
    with pytest.raises(ToolError, match="needs id"):
        await impl.craft_record(
            claim="x",
            confidence="inferred",
            evidence=[{"kind": "render"}],
            user_id="alice",
            session_id="s1",
        )


# --- craft_assert ---


@pytest.mark.asyncio()
async def test_assert_structural_pass_and_fail(setup) -> None:
    impl, phase1, *_ = setup
    passed = await impl.craft_assert(
        app="photocraft",
        expect={"revision": 1, "doc_count": 1},
        user_id="alice",
        session_id="s1",
    )
    assert passed["passed"] is True
    assert passed["observed"] == {"revision": 1, "doc_count": 1}
    await phase1.craft_run(
        app="photocraft", command="noop", user_id="alice", session_id="s1"
    )
    failed = await impl.craft_assert(
        app="photocraft", expect={"revision": 1}, user_id="alice", session_id="s1"
    )
    assert failed["passed"] is False
    assert failed["observed"] == {"revision": 2}


@pytest.mark.asyncio()
async def test_assert_all_composition_and_unknown(setup) -> None:
    impl, *_ = setup
    combo = await impl.craft_assert(
        app="photocraft",
        expect={"all": [{"revision": 1}, {"doc_count": 1}]},
        user_id="alice",
        session_id="s1",
    )
    assert combo["passed"] is True
    with pytest.raises(ToolError, match="unknown assertion"):
        await impl.craft_assert(
            app="photocraft",
            expect={"vibes": "good"},
            user_id="alice",
            session_id="s1",
        )
    with pytest.raises(ToolError, match="non-empty mapping"):
        await impl.craft_assert(
            app="photocraft", expect={}, user_id="alice", session_id="s1"
        )


@pytest.mark.asyncio()
async def test_assert_visual_requires_tolerance(setup) -> None:
    impl, *_ = setup
    with pytest.raises(ToolError, match="require tolerance"):
        await impl.craft_assert(
            app="photocraft",
            expect={"mean_luma_delta_from": {"revision": 1}},
            user_id="alice",
            session_id="s1",
        )
    same = await impl.craft_assert(
        app="photocraft",
        expect={"mean_luma_delta_from": {"revision": 1, "within": 0.02}},
        user_id="alice",
        session_id="s1",
    )
    assert same["passed"] is True
    region = await impl.craft_assert(
        app="photocraft",
        expect={"region_non_empty": {"rect": [0, 0, 100, 100]}},
        tolerance=0.05,
        user_id="alice",
        session_id="s1",
    )
    assert region["passed"] is True


@pytest.mark.asyncio()
async def test_assert_output_path_roots_escape_denied(setup) -> None:
    impl, *_ = setup
    with pytest.raises(ToolError, match="access denied"):
        await impl.craft_assert(
            app="photocraft",
            expect={"output_path": "../../escape.png"},
            user_id="alice",
            session_id="s1",
        )


# --- auto-snapshot policy ---


def test_is_destructive_command_predicate() -> None:
    assert is_destructive_command("app.save", {}) is True
    assert is_destructive_command("delete", {}) is True
    assert is_destructive_command("doc_inspect", {}) is False
    assert is_destructive_command("render_preview", {}) is False
    assert (
        is_destructive_command(
            "batch", {"steps": [{"command": "save"}, {"command": "delete"}]}
        )
        is True
    )
    assert is_destructive_command("batch", {"steps": [{"command": "save"}]}) is False


@pytest.mark.asyncio()
async def test_craft_run_auto_snapshot_on_destructive(setup) -> None:
    """Policy hook: destructive craft_run returns a usable snapshot token."""
    impl, phase1, *_ = setup
    result = await phase1.craft_run(
        app="photocraft",
        command="app.save",
        params={},
        user_id="alice",
        session_id="s1",
    )
    assert "snapshot_token" in result
    restored = await impl.craft_restore(
        app="photocraft",
        token=result["snapshot_token"],
        user_id="alice",
        session_id="s1",
    )
    assert restored["restored_to"] == 1


@pytest.mark.asyncio()
async def test_craft_run_no_snapshot_for_reads(setup) -> None:
    _, phase1, *_ = setup
    result = await phase1.craft_run(
        app="photocraft",
        command="doc_inspect",
        params={},
        user_id="alice",
        session_id="s1",
    )
    assert "snapshot_token" not in result


# --- auth / unauthorized ---


@pytest.mark.asyncio()
async def test_phase2_allowlist_denial_and_bogus_token(setup) -> None:
    impl, _, _, _, store, *_ = setup
    ok = await impl.craft_look(
        app="photocraft",
        user_id="alice",
        session_id="s1",
        raw_token=ALICE_TOKEN,
    )
    assert ok["app"] == "photocraft"
    # Bogus token: authentication fails closed.
    with pytest.raises(ToolError, match="access denied"):
        await impl.craft_record(
            claim="x",
            confidence="inferred",
            user_id="mallory",
            session_id="s1",
            raw_token=BOGUS_TOKEN,
        )
    # Valid token, wrong tool: viewer token allows craft_look only.
    viewer_raw, _ = store.mint("viewer", {"craft_look"})
    with pytest.raises(ToolError, match="access denied"):
        await impl.craft_record(
            claim="x",
            confidence="inferred",
            user_id="viewer",
            session_id="s1",
            raw_token=viewer_raw,
        )


# --- logger redaction ---


@pytest.mark.asyncio()
async def test_phase2_logs_carry_no_secrets_content_or_pixels(
    setup, caplog: pytest.LogCaptureFixture
) -> None:
    impl, *_ = setup
    secret_claim = "sk-secret-claim-xyz with private bytes"
    secret_note = "note-with-image-payload-iVBORw0KGgo"
    with caplog.at_level(logging.INFO, logger="gateway"):
        snap = await impl.craft_snapshot(
            app="photocraft", user_id="alice", session_id="s1"
        )
        await impl.craft_look(app="photocraft", user_id="alice", session_id="s1")
        await impl.craft_record(
            claim=secret_claim,
            confidence="measured",
            evidence=[{"kind": "render", "id": "r1"}],
            note=secret_note,
            user_id="alice",
            session_id="s1",
        )
        await impl.craft_assert(
            app="photocraft",
            expect={"revision": 1},
            user_id="alice",
            session_id="s1",
        )
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "sk-secret-claim-xyz" not in text
    assert "private bytes" not in text
    assert "iVBORw0KGgo" not in text
    assert snap["token"] not in text  # token secret; prefix-only in logs


# --- wiring ---


@pytest.mark.asyncio()
async def test_register_phase2_tools_wires_all_five(tmp_path) -> None:
    from fastmcp import Client

    from gateway.main import create_gateway

    work = tmp_path / "work"
    work.mkdir()
    sessions = SessionRegistry(default_roots=[work])
    sessions.create("s1", "alice")
    manager = BackendManager(use_fake=True)
    mcp = create_gateway(backend_manager=manager, sessions=sessions, require_auth=False)
    register_phase2_tools(mcp, backend_manager=manager, sessions=sessions)
    async with Client(mcp) as client:
        tools = await client.list_tools()
        assert set(TOOL_NAMES) <= {t.name for t in tools}
        snap = await client.call_tool("craft_snapshot", {"app": "photocraft"})
        assert "snap_" in str(snap.content)
        look = await client.call_tool("craft_look", {"app": "photocraft"})
        assert "sha256:fake" in str(look.content)
    await manager.close_all()
