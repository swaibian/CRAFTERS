"""SWE4 unit tests for gateway/tools_phase1.py (SWE3-A-02).

Positive: each tool's happy path against fake pilot backends; craft_status
single + all; registry metadata.
Negative: unknown app; unknown backend method; allowlist denial on direct
calls; roots escape via path params; no token/content leakage in logs.
"""

from __future__ import annotations

import logging

import pytest
from fastmcp.exceptions import ToolError

from gateway.auth import AuthStore, TokenRecord
from gateway.backends import BackendManager, SessionRegistry
from gateway.tools_phase1 import (
    APP_REGISTRY,
    TOOL_NAMES,
    Phase1Tools,
    register_phase1_tools,
)

ALICE_TOKEN = "alice-phase1-token"


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
            allowlist=frozenset({"craft_apps", "craft_status"}),
        ),
    )
    manager = BackendManager(use_fake=True)
    sessions = SessionRegistry(default_roots=[work])
    sessions.create("s1", "alice", key_id="key_alice")
    impl = Phase1Tools(manager, sessions, store)
    return impl, manager, sessions, store


def test_tool_names_complete() -> None:
    assert set(TOOL_NAMES) == {
        "craft_apps",
        "craft_status",
        "craft_run",
        "craft_run_tool",
        "craft_app_call",
    }


def test_registry_pilot_only_generic_shape() -> None:
    assert set(APP_REGISTRY) == {"photocraft", "pdfcraft", "gridcraft"}
    for app_id, entry in APP_REGISTRY.items():
        assert entry["cli"] == f"{app_id}-cli"
        assert entry["args"] == ["mcp"]
        assert entry["description"] and entry["capabilities"]


@pytest.mark.asyncio()
async def test_craft_apps_lists_pilots(setup) -> None:
    impl, *_ = setup
    result = await impl.craft_apps(user_id="alice", session_id="s1")
    assert {a["app"] for a in result["apps"]} == {"photocraft", "pdfcraft", "gridcraft"}
    assert all(a["available"] for a in result["apps"])
    assert all(a["description"] for a in result["apps"])


@pytest.mark.asyncio()
async def test_craft_status_all_and_single(setup) -> None:
    impl, *_ = setup
    all_apps = await impl.craft_status(user_id="alice", session_id="s1")
    assert len(all_apps["apps"]) == 3
    first = all_apps["apps"][0]
    assert {
        "app",
        "available",
        "running",
        "documents",
        "jobs",
        "mode",
        "roots",
        "last_error",
    } <= set(first)
    assert first["roots"] == {
        "read": first["roots"]["read"],
        "write": first["roots"]["write"],
    }
    single = await impl.craft_status(app="pdfcraft", user_id="alice", session_id="s1")
    assert [a["app"] for a in single["apps"]] == ["pdfcraft"]
    assert single["apps"][0]["documents"]


@pytest.mark.asyncio()
async def test_craft_run_guarded_execute(setup) -> None:
    impl, *_ = setup
    result = await impl.craft_run(
        app="photocraft",
        command="filter.blur",
        params={"radius": 2},
        user_id="alice",
        session_id="s1",
    )
    assert result["ok"] is True
    assert result["revision"] == 2


@pytest.mark.asyncio()
async def test_craft_run_tool_passthrough(setup) -> None:
    impl, *_ = setup
    result = await impl.craft_run_tool(
        app="gridcraft", tool="doc_inspect", args={}, user_id="alice", session_id="s1"
    )
    assert result["app"] == "gridcraft"


@pytest.mark.asyncio()
async def test_craft_app_call_escape_hatch(setup) -> None:
    impl, *_ = setup
    result = await impl.craft_app_call(
        app="pdfcraft",
        method="doc_inspect",
        params={},
        user_id="alice",
        session_id="s1",
    )
    assert result["app"] == "pdfcraft"


@pytest.mark.asyncio()
async def test_unknown_app_rejected(setup) -> None:
    impl, *_ = setup
    with pytest.raises(ToolError, match="unknown app"):
        await impl.craft_status(app="nosuchcraft", user_id="alice", session_id="s1")
    with pytest.raises(ToolError, match="unknown app"):
        await impl.craft_run(
            app="nosuchcraft", command="x", user_id="alice", session_id="s1"
        )


@pytest.mark.asyncio()
async def test_unknown_backend_method_surfaced_safely(setup) -> None:
    impl, *_ = setup
    with pytest.raises(ToolError, match="unknown method"):
        await impl.craft_run_tool(
            app="photocraft", tool="nope", user_id="alice", session_id="s1"
        )


@pytest.mark.asyncio()
async def test_allowlist_denial_on_direct_call(setup) -> None:
    impl, *_ = setup
    # Alice's token allows craft_status but not craft_run.
    ok = await impl.craft_status(
        user_id="alice", session_id="s1", raw_token=ALICE_TOKEN
    )
    assert len(ok["apps"]) == 3
    with pytest.raises(ToolError, match="access denied"):
        await impl.craft_run(
            app="photocraft",
            command="x",
            user_id="alice",
            session_id="s1",
            raw_token=ALICE_TOKEN,
        )
    with pytest.raises(ToolError, match="access denied"):
        await impl.craft_run(
            app="photocraft",
            command="x",
            user_id="mallory",
            session_id="s1",
            raw_token="bogus-token",
        )


@pytest.mark.asyncio()
async def test_roots_confinement_on_path_params(setup, tmp_path) -> None:
    impl, *_ = setup
    # Inside roots: confined to absolute path under work/.
    result = await impl.craft_run(
        app="photocraft",
        command="save",
        params={"output_path": "out.png"},
        user_id="alice",
        session_id="s1",
    )
    assert result["ok"] is True
    # Escape: denied with generic message (no filesystem details).
    with pytest.raises(ToolError, match="access denied"):
        await impl.craft_run(
            app="photocraft",
            command="save",
            params={"output_path": "../../etc/evil.png"},
            user_id="alice",
            session_id="s1",
        )


@pytest.mark.asyncio()
async def test_tool_logs_carry_no_secrets(
    setup, caplog: pytest.LogCaptureFixture
) -> None:
    impl, *_ = setup
    with caplog.at_level(logging.INFO, logger="gateway"):
        await impl.craft_run(
            app="photocraft",
            command="import",
            params={"token": "sk-secret-xyz", "document": "private bytes"},
            user_id="alice",
            session_id="s1",
        )
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "sk-secret-xyz" not in text
    assert "private bytes" not in text


@pytest.mark.asyncio()
async def test_confine_forwards_params_intact_without_sessions() -> None:
    """Gap fix (TC-A-02): redaction is for logs, never for forwarding."""
    manager = BackendManager(use_fake=True)
    impl = Phase1Tools(manager, None, None)
    result = await impl.craft_run_tool(
        app="photocraft",
        tool="doc_inspect",
        args={"args": "keep-me", "params": {"nested": 1}},
        user_id="alice",
        session_id="s1",
    )
    assert result["app"] == "photocraft"
    await manager.close_all()


@pytest.mark.asyncio()
async def test_register_phase1_tools_wires_all_five(tmp_path) -> None:
    from fastmcp import Client

    from gateway.main import create_gateway

    work = tmp_path / "work"
    work.mkdir()
    sessions = SessionRegistry(default_roots=[work])
    manager = BackendManager(use_fake=True)
    mcp = create_gateway(backend_manager=manager, sessions=sessions, require_auth=False)
    register_phase1_tools(mcp, backend_manager=manager, sessions=sessions)
    async with Client(mcp) as client:
        tools = await client.list_tools()
        assert {t.name for t in tools} == set(TOOL_NAMES)
        result = await client.call_tool("craft_status", {"app": "photocraft"})
        assert "photocraft" in str(result.content)
    await manager.close_all()
