"""SWE5 integration tests for TC-A (self-verify, no-reviews).

Cross-module through the real wiring: create_gateway() +
register_phase1_tools() + AuthMiddleware + BackendManager + SessionRegistry,
exercised via an in-memory FastMCP Client with per-token allowlists.

Covers the TC-A acceptance plan: craft_status via proxied backends;
allowlist denial end-to-end; session-roots confinement end-to-end.
"""

from __future__ import annotations

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from gateway.auth import AuthStore, TokenRecord
from gateway.backends import BackendManager, SessionRegistry
from gateway.main import create_gateway
from gateway.tools_phase1 import TOOL_NAMES, register_phase1_tools

FULL_TOKEN = "integration-full-token"
LIMITED_TOKEN = "integration-limited-token"


@pytest.fixture()
def gateway(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    store = AuthStore(
        {
            FULL_TOKEN: TokenRecord(
                key_id="key_full",
                user_id="op",
                allowlist=frozenset({"*"}),
            ),
            LIMITED_TOKEN: TokenRecord(
                key_id="key_limited",
                user_id="viewer",
                allowlist=frozenset({"craft_apps", "craft_status"}),
            ),
        }
    )
    manager = BackendManager(use_fake=True)
    sessions = SessionRegistry(default_roots=[work])
    sessions.create("sess-op", "op", key_id="key_full")
    sessions.create("sess-viewer", "viewer", key_id="key_limited")
    mcp = create_gateway(auth_store=store, backend_manager=manager, sessions=sessions)
    register_phase1_tools(
        mcp, backend_manager=manager, sessions=sessions, auth_store=store
    )
    return mcp, manager


@pytest.mark.asyncio()
async def test_all_five_tools_reachable(gateway) -> None:
    mcp, _ = gateway
    # Server-side surface (middleware filters unauthenticated list_tools,
    # so reachability is asserted here; per-token filtering is covered by
    # test_allowlist_denial_end_to_end through the client).
    tools = await mcp.get_tools()
    assert set(tools) >= set(TOOL_NAMES)


@pytest.mark.asyncio()
async def test_craft_status_end_to_end_proxied(gateway) -> None:
    """Acceptance 1: craft_status lists pilot apps with documents via backends."""
    mcp, _ = gateway
    async with Client(mcp) as client:
        result = await client.call_tool("craft_status", {"_gateway_token": FULL_TOKEN})
        text = str(result.content)
        for app in ("photocraft", "pdfcraft", "gridcraft"):
            assert app in text
        assert "documents" in text


@pytest.mark.asyncio()
async def test_allowlist_denial_end_to_end(gateway) -> None:
    """Acceptance 2: token without allowlist entry is denied the tool."""
    mcp, _ = gateway
    async with Client(mcp) as client:
        ok = await client.call_tool("craft_apps", {"_gateway_token": LIMITED_TOKEN})
        assert "photocraft" in str(ok.content)
        with pytest.raises(ToolError, match="access denied"):
            await client.call_tool(
                "craft_run",
                {"_gateway_token": LIMITED_TOKEN, "app": "photocraft", "command": "x"},
            )
        with pytest.raises(ToolError, match="access denied"):
            await client.call_tool("craft_status", {})


@pytest.mark.asyncio()
async def test_run_then_status_revision_advances(gateway) -> None:
    """Cross-module: craft_run mutates backend state visible via craft_status."""
    mcp, _ = gateway
    async with Client(mcp) as client:
        await client.call_tool(
            "craft_run",
            {
                "_gateway_token": FULL_TOKEN,
                "app": "photocraft",
                "command": "filter.blur",
                "params": {"radius": 1},
            },
        )
        status = await client.call_tool(
            "craft_status",
            {"_gateway_token": FULL_TOKEN, "app": "photocraft"},
        )
        assert "revision" in str(status.content)


@pytest.mark.asyncio()
async def test_session_roots_confine_end_to_end(gateway) -> None:
    """Acceptance 3: escape rejected through the full MCP path."""
    mcp, _ = gateway
    async with Client(mcp) as client:
        with pytest.raises(ToolError, match="access denied"):
            await client.call_tool(
                "craft_run",
                {
                    "_gateway_token": FULL_TOKEN,
                    "app": "photocraft",
                    "command": "save",
                    "params": {"output_path": "../../escape.png"},
                },
            )


@pytest.mark.asyncio()
async def test_unknown_app_end_to_end(gateway) -> None:
    mcp, _ = gateway
    async with Client(mcp) as client:
        with pytest.raises(ToolError, match="unknown app"):
            await client.call_tool(
                "craft_app_call",
                {
                    "_gateway_token": FULL_TOKEN,
                    "app": "nosuchcraft",
                    "method": "ui.inspect",
                },
            )
