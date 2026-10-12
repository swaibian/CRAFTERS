"""SWE5 integration tests for TC-C (self-verify, no-reviews).

Perception end-to-end through the real wiring: ``create_gateway()`` +
``register_perception_tools()`` + ``AuthMiddleware``, exercised via an
in-memory FastMCP Client alongside Phase-1/2 (shared session roots).

Covers the TC-C acceptance plan: widget tree reachable via the gateway
tool; document↔screen mapping resolves; pattern-doc third-app scoping
(gridcraft) is source-grounded.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from gateway.auth import AuthStore, TokenRecord
from gateway.backends import BackendManager, SessionRegistry
from gateway.main import create_gateway
from gateway.perception import TOOL_NAMES, register_perception_tools
from gateway.snapshots import SnapshotStore
from gateway.tools_phase1 import register_phase1_tools
from gateway.tools_phase2 import register_phase2_tools

FULL_TOKEN = "tc-c-full-token"
LIMITED_TOKEN = "tc-c-limited-token"


@pytest.fixture()
def gateway(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    store = AuthStore(
        {
            FULL_TOKEN: TokenRecord(
                key_id="key_full", user_id="op", allowlist=frozenset({"*"})
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
    mcp = create_gateway(auth_store=store, backend_manager=manager, sessions=sessions)
    shared = SnapshotStore()
    register_phase1_tools(
        mcp,
        backend_manager=manager,
        sessions=sessions,
        auth_store=store,
        snapshots=shared,
    )
    register_phase2_tools(
        mcp,
        backend_manager=manager,
        sessions=sessions,
        auth_store=store,
        snapshots=shared,
    )
    register_perception_tools(
        mcp, backend_manager=manager, sessions=sessions, auth_store=store
    )
    return mcp


@pytest.mark.asyncio()
async def test_perception_tools_reachable(gateway) -> None:
    tools = await gateway.get_tools()
    assert set(tools) >= set(TOOL_NAMES)


@pytest.mark.asyncio()
async def test_widgets_reachable_via_gateway(gateway) -> None:
    """Acceptance 1: AccessKit tree reachable via the gateway MCP tool."""
    async with Client(gateway) as client:
        result = await client.call_tool(
            "craft_widgets",
            {"_gateway_token": FULL_TOKEN, "app": "pdfcraft"},
        )
        payload = json.loads(result.content[0].text)
        assert payload["app"] == "pdfcraft"
        assert payload["count"] >= 1
        assert all("id" in w and "role" in w for w in payload["widgets"])
        assert len(payload["query_map_ids"]) == payload["count"]


@pytest.mark.asyncio()
async def test_mapping_resolves_via_gateway(gateway) -> None:
    """Acceptance 2: document<->screen mapping resolves for photocraft."""
    async with Client(gateway) as client:
        fwd = await client.call_tool(
            "craft_map",
            {
                "_gateway_token": FULL_TOKEN,
                "app": "photocraft",
                "direction": "canvas_rect",
                "zoom": 2.0,
                "canvas_size": [200.0, 100.0],
            },
        )
        payload = json.loads(fwd.content[0].text)
        assert payload["result"]["w"] == pytest.approx(400.0)
        assert payload["query_map_id"].startswith("qm_")


@pytest.mark.asyncio()
async def test_perception_allowlist_denial(gateway) -> None:
    async with Client(gateway) as client:
        with pytest.raises(ToolError, match="access denied"):
            await client.call_tool(
                "craft_widgets",
                {"_gateway_token": LIMITED_TOKEN, "app": "pdfcraft"},
            )


def test_pattern_third_app_scoping_source_grounded() -> None:
    """Acceptance 3: the pattern doc's gridcraft scoping cites real sources."""
    pattern = (
        Path(__file__).resolve().parent.parent.parent
        / "docs"
        / "a11y-contribution-pattern.md"
    )
    text = pattern.read_text(encoding="utf-8")
    assert "gridcraft-main" in text
    assert "cells_rect" in text or "grid" in text
    assert "W-lite" in text
    for ref in (
        "docs/upstream-prs/pdfcraft-accesskit-via-mcp.md",
        "docs/upstream-prs/photocraft-canvasrect.md",
    ):
        draft = Path(__file__).resolve().parent.parent.parent / ref
        assert draft.exists(), f"missing PR draft {ref}"
