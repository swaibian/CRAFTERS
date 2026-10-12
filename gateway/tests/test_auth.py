"""SWE4 unit tests for gateway/auth.py (SWE3-A-01).

Positive: valid bearer authenticates; allowlisted tool authorized; wildcard
allows all; stdio `_gateway_token` path works through the middleware.
Negative: missing/unknown/revoked/expired tokens; unlisted tool denied;
per-user denial (user B's token cannot use user A's tools and vice versa);
no token material in errors, logs, or tool listings.
"""

from __future__ import annotations

import logging
import time

import pytest

from gateway.auth import (
    AuthError,
    AuthMiddleware,
    AuthStore,
    TokenRecord,
    check_tool_allowed,
    extract_bearer,
)

ALICE_TOKEN = "alice-secret-token-001"
BOB_TOKEN = "bob-secret-token-002"


@pytest.fixture()
def store() -> AuthStore:
    return AuthStore(
        {
            ALICE_TOKEN: TokenRecord(
                key_id="key_alice",
                user_id="alice",
                allowlist=frozenset({"craft_status"}),
            ),
            BOB_TOKEN: TokenRecord(
                key_id="key_bob",
                user_id="bob",
                allowlist=frozenset({"craft_apps"}),
            ),
        }
    )


# --- authenticate: positive ---


def test_authenticate_valid_bearer(store: AuthStore) -> None:
    record = store.authenticate(ALICE_TOKEN)
    assert record.user_id == "alice"
    assert record.key_id == "key_alice"


def test_authenticate_accepts_bearer_prefix(store: AuthStore) -> None:
    record = store.authenticate(f"Bearer {ALICE_TOKEN}")
    assert record.user_id == "alice"


def test_mint_roundtrip() -> None:
    store = AuthStore()
    raw, record = store.mint("carol", {"craft_status"})
    assert store.authenticate(raw).user_id == "carol"
    assert record.user_id == "carol"


# --- authenticate: negative ---


@pytest.mark.parametrize("bad", [None, "", "   ", "Bearer ", "no-such-token"])
def test_authenticate_rejects_bad_tokens(store: AuthStore, bad: str | None) -> None:
    with pytest.raises(AuthError):
        store.authenticate(bad)  # type: ignore[arg-type]


def test_authenticate_revoked_denied(store: AuthStore) -> None:
    assert store.revoke("key_alice") is True
    with pytest.raises(AuthError):
        store.authenticate(ALICE_TOKEN)
    # Bob unaffected by Alice's revocation (per-user denial).
    assert store.authenticate(BOB_TOKEN).user_id == "bob"


def test_authenticate_expired_denied() -> None:
    store = AuthStore(
        {
            "old-token": TokenRecord(
                key_id="key_old",
                user_id="zed",
                allowlist=frozenset({"*"}),
                expires_at=time.time() - 10,
            )
        }
    )
    with pytest.raises(AuthError, match="expired"):
        store.authenticate("old-token")


def test_authenticate_errors_leak_nothing(store: AuthStore) -> None:
    for bad in ("wrong-token-xyz", ALICE_TOKEN + "-tampered"):
        try:
            store.authenticate(bad)
            raise AssertionError("should have raised")
        except AuthError as exc:
            assert bad not in str(exc)
            assert ALICE_TOKEN not in str(exc)


# --- authorize: allowlist ---


def test_authorize_allows_listed_tool(store: AuthStore) -> None:
    record = store.authenticate(ALICE_TOKEN)
    store.authorize(record, "craft_status")  # must not raise


def test_authorize_denies_unlisted_tool(store: AuthStore) -> None:
    record = store.authenticate(ALICE_TOKEN)
    with pytest.raises(AuthError, match="not allowed"):
        store.authorize(record, "craft_run")
    # Error names the tool but not the token or allowlist contents.
    try:
        store.authorize(record, "craft_run")
    except AuthError as exc:
        assert ALICE_TOKEN not in str(exc)
        assert "craft_status" not in str(exc)


def test_authorize_wildcard_allows_all() -> None:
    store = AuthStore(
        {
            "root-tok": TokenRecord(
                key_id="k", user_id="root", allowlist=frozenset({"*"})
            )
        }
    )
    record = store.authenticate("root-tok")
    store.authorize(record, "anything_at_all")


def test_per_user_denial(store: AuthStore) -> None:
    """Alice's token cannot use Bob's tool and vice versa."""
    alice = store.authenticate(ALICE_TOKEN)
    bob = store.authenticate(BOB_TOKEN)
    with pytest.raises(AuthError):
        store.authorize(alice, "craft_apps")
    with pytest.raises(AuthError):
        store.authorize(bob, "craft_status")
    # Positive sides still work.
    store.authorize(alice, "craft_status")
    store.authorize(bob, "craft_apps")


def test_check_tool_allowed_helper(store: AuthStore) -> None:
    assert check_tool_allowed(store, ALICE_TOKEN, "craft_status").user_id == "alice"
    with pytest.raises(AuthError):
        check_tool_allowed(store, ALICE_TOKEN, "craft_run")
    with pytest.raises(AuthError):
        check_tool_allowed(store, "bogus", "craft_status")


def test_extract_bearer() -> None:
    assert extract_bearer(None) is None
    assert extract_bearer({}) is None
    assert extract_bearer({"authorization": "Bearer abc123"}) == "abc123"
    assert extract_bearer({"authorization": "Basic xyz"}) is None


# --- middleware through a real FastMCP app ---


def _app_with_probe(store: AuthStore, *, require_auth: bool = True):
    from fastmcp import FastMCP

    mcp = FastMCP("auth-test")
    mcp.add_middleware(AuthMiddleware(store, require_auth=require_auth))

    @mcp.tool()
    def craft_status() -> str:
        """Probe tool."""
        return "ok-status"

    @mcp.tool()
    def craft_run() -> str:
        """Probe tool."""
        return "ok-run"

    return mcp


@pytest.mark.asyncio()
async def test_middleware_allows_listed_tool_via_token(store: AuthStore) -> None:
    from fastmcp import Client

    mcp = _app_with_probe(store)
    async with Client(mcp) as client:
        result = await client.call_tool("craft_status", {"_gateway_token": ALICE_TOKEN})
        assert "ok-status" in str(result.content)


@pytest.mark.asyncio()
async def test_middleware_denies_unlisted_tool(store: AuthStore) -> None:
    from fastmcp import Client
    from fastmcp.exceptions import ToolError

    mcp = _app_with_probe(store)
    async with Client(mcp) as client:
        with pytest.raises(ToolError, match="access denied"):
            await client.call_tool("craft_run", {"_gateway_token": ALICE_TOKEN})


@pytest.mark.asyncio()
async def test_middleware_denies_missing_token(store: AuthStore) -> None:
    from fastmcp import Client
    from fastmcp.exceptions import ToolError

    mcp = _app_with_probe(store)
    async with Client(mcp) as client:
        with pytest.raises(ToolError, match="access denied"):
            await client.call_tool("craft_status", {})


@pytest.mark.asyncio()
async def test_middleware_denial_logged_without_secrets(
    store: AuthStore, caplog: pytest.LogCaptureFixture
) -> None:
    from fastmcp import Client
    from fastmcp.exceptions import ToolError

    mcp = _app_with_probe(store)
    with caplog.at_level(logging.INFO, logger="gateway.audit"):
        async with Client(mcp) as client:
            with pytest.raises(ToolError):
                await client.call_tool("craft_run", {"_gateway_token": ALICE_TOKEN})
    audit_text = "\n".join(
        r.getMessage() for r in caplog.records if r.name == "gateway.audit"
    )
    assert "auth_decision" in audit_text
    assert ALICE_TOKEN not in audit_text
    assert "craft_status" not in audit_text  # allowlist contents never logged
