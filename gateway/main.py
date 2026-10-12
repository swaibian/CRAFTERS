"""Crafter gateway entrypoint: FastMCP app, transports, lifespan.

Wiring chain (STEP B5)::

    python -m gateway.main --transport stdio|http [--port N]
      → create_gateway(auth_store, backend_manager, sessions)
      → FastMCP("crafter-gateway") + AuthMiddleware + lifespan
      → mcp.run(transport="stdio") | mcp.run_http_async(transport="http")

TC-A-02 wires Phase-1 tools between ``create_gateway()`` and the transports
via ``register_phase1_tools(mcp, ...)``. TC-B-01 adds Phase-2 verification
tools via ``register_phase2_tools(mcp, ...)`` sharing one SnapshotStore so
the ``craft_run`` auto-snapshot hook and ``craft_restore`` see the same
tokens.

Token bootstrap (TC-B-02): an empty ``AuthStore`` denies everything (fail
closed). For local runs, ``main()`` provisions tokens from, in order:
``CRAFTER_DEV_TOKEN`` env (wildcard, local use only — refused unless the
transport is loopback or ``--dev-token-ok`` is passed), then
``CRAFTER_TOKENS_FILE`` (JSON ``{raw_token: {user_id, allowlist}}``).
Provisioned tokens are printed once to stdout (dev token) or summarized by
``key_id`` (file). Production deployments must provision via the file or
their own ``create_gateway`` wiring — never the dev token.

SW-REQ: SW-REQ-GW-CORE (service + transports, TC-A-01).
SW-REQ: SW-REQ-GW-VERIFY (verification tools, TC-B-01).
SW-REQ: SW-REQ-GW-VERIFY (containment + local run, TC-B-02).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path

from fastmcp import FastMCP

from .auth import AuthMiddleware, AuthStore, TokenRecord
from .backends import BackendManager, SessionRegistry
from .logger import get_logger, safe_event

log = get_logger()

GATEWAY_NAME = "crafter-gateway"


def create_gateway(
    auth_store: AuthStore | None = None,
    backend_manager: BackendManager | None = None,
    sessions: SessionRegistry | None = None,
    *,
    require_auth: bool = True,
) -> FastMCP:
    """Build the gateway FastMCP app with auth middleware and lifespan.

    :param auth_store: Token registry (a fresh empty one if omitted).
    :param backend_manager: App backend owner (default pilot manager).
    :param sessions: Session registry (fresh one if omitted).
    :param require_auth: Passed to :class:`AuthMiddleware`; False allows
        unauthenticated local stdio use (tests).
    :returns: Configured :class:`FastMCP` app. Handles are stashed as
        ``mcp.auth_store`` / ``mcp.backend_manager`` / ``mcp.sessions`` for
        tool registration (TC-A-02) and tests.
    """
    store = auth_store or AuthStore()
    backends = backend_manager or BackendManager()
    registry = sessions or SessionRegistry()

    @contextlib.asynccontextmanager
    async def _lifespan(_: FastMCP) -> AsyncIterator[None]:
        log.info("gateway startup: %s", safe_event(event="gateway_startup"))
        try:
            yield
        finally:
            await backends.close_all()
            log.info("gateway shutdown: %s", safe_event(event="gateway_shutdown"))

    mcp = FastMCP(GATEWAY_NAME, lifespan=_lifespan)
    mcp.add_middleware(AuthMiddleware(store, require_auth=require_auth))

    # Stash handles for tool wiring + tests (not part of the MCP surface).
    mcp.auth_store = store  # type: ignore[attr-defined]
    mcp.backend_manager = backends  # type: ignore[attr-defined]
    mcp.sessions = registry  # type: ignore[attr-defined]
    return mcp


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the gateway entrypoint."""
    parser = argparse.ArgumentParser(
        prog="crafter-gateway", description="Crafter gateway (FastMCP)"
    )
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--path", default="/mcp")
    parser.add_argument(
        "--open-auth",
        action="store_true",
        help="Allow unauthenticated local stdio use.",
    )
    parser.add_argument(
        "--tokens-file",
        default=None,
        help="JSON token-provisioning file (overrides CRAFTER_TOKENS_FILE).",
    )
    parser.add_argument(
        "--dev-token-ok",
        action="store_true",
        help="Permit CRAFTER_DEV_TOKEN on non-loopback binds (local testing).",
    )
    parser.add_argument(
        "--work-dir",
        default=None,
        help="Default session roots dir (overrides CRAFTER_WORK_DIR).",
    )
    return parser


def _is_loopback(host: str) -> bool:
    """Whether ``host`` binds loopback only."""
    return host in ("127.0.0.1", "::1", "localhost")


def provision_tokens(
    store: AuthStore,
    *,
    host: str,
    dev_token_ok: bool = False,
    tokens_file: str | None = None,
) -> list[str]:
    """Provision local-run tokens into ``store`` (fail-closed by default).

    Order: ``CRAFTER_DEV_TOKEN`` env (wildcard token, local use only —
    refused unless ``host`` is loopback or ``dev_token_ok``), then the JSON
    tokens file (``tokens_file`` arg or ``CRAFTER_TOKENS_FILE`` env) mapping
    raw tokens to ``{"user_id", "allowlist"}`` entries.

    :param store: Token registry to provision into.
    :param host: Bind host (loopback check for the dev token).
    :param dev_token_ok: Override the loopback requirement (testing only).
    :param tokens_file: Explicit path to the JSON tokens file.
    :returns: Human-readable summary lines (``key_id`` only, never tokens).
    :raises SystemExit: Dev token presented on a non-loopback bind without
        the override; malformed tokens file.
    """
    summary: list[str] = []
    dev_token = os.environ.get("CRAFTER_DEV_TOKEN", "")
    if dev_token:
        if not (_is_loopback(host) or dev_token_ok):
            raise SystemExit(
                "CRAFTER_DEV_TOKEN refused: non-loopback bind without "
                "--dev-token-ok (tokens must never cross the network in "
                "dev mode)"
            )
        store.register(
            dev_token,
            TokenRecord(key_id="key_dev", user_id="dev", allowlist=frozenset({"*"})),
        )
        summary.append("dev token provisioned for user dev (wildcard)")
    path = tokens_file or os.environ.get("CRAFTER_TOKENS_FILE", "")
    if path:
        try:
            entries = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"cannot load tokens file {path}: {exc}") from None
        if not isinstance(entries, dict):
            raise SystemExit(f"tokens file {path} must hold a JSON object")
        for raw, spec in entries.items():
            if not isinstance(spec, dict) or "user_id" not in spec:
                raise SystemExit(
                    f"tokens file {path}: entry for a token must map to "
                    '{"user_id", "allowlist"}'
                )
            record = TokenRecord(
                key_id=f"key_{spec.get('key_id', spec['user_id'])}",
                user_id=str(spec["user_id"]),
                allowlist=frozenset(spec.get("allowlist", ["*"])),
            )
            store.register(str(raw), record)
            summary.append(
                f"token provisioned: key_id={record.key_id} "
                f"user={record.user_id} tools={len(record.allowlist)}"
            )
    return summary


def main(argv: list[str] | None = None) -> None:
    """Process entrypoint: build the app and run the chosen transport.

    :param argv: CLI args (defaults to ``sys.argv``).
    """
    args = build_parser().parse_args(argv)
    work_dir = args.work_dir or os.environ.get("CRAFTER_WORK_DIR", "")
    sessions: SessionRegistry | None = None
    if work_dir:
        root = Path(work_dir)
        root.mkdir(parents=True, exist_ok=True)
        sessions = SessionRegistry(default_roots=[root])
        sessions.create("default", "local", key_id="key_local")
    mcp = create_gateway(
        require_auth=not args.open_auth,
        sessions=sessions,
    )
    for line in provision_tokens(
        mcp.auth_store,  # type: ignore[attr-defined]
        host=args.host,
        dev_token_ok=args.dev_token_ok,
        tokens_file=args.tokens_file,
    ):
        print(f"crafter-gateway: {line}")
    try:
        from .perception import register_perception_tools
        from .snapshots import SnapshotStore
        from .tools_phase1 import register_phase1_tools
        from .tools_phase2 import register_phase2_tools

        shared_snapshots = SnapshotStore()
        register_phase1_tools(
            mcp,
            backend_manager=mcp.backend_manager,  # type: ignore[attr-defined]
            sessions=mcp.sessions,  # type: ignore[attr-defined]
            snapshots=shared_snapshots,
        )
        register_phase2_tools(
            mcp,
            backend_manager=mcp.backend_manager,  # type: ignore[attr-defined]
            sessions=mcp.sessions,  # type: ignore[attr-defined]
            snapshots=shared_snapshots,
        )
        register_perception_tools(
            mcp,
            backend_manager=mcp.backend_manager,  # type: ignore[attr-defined]
            sessions=mcp.sessions,  # type: ignore[attr-defined]
        )
    except ImportError:
        # TC-A-01 stage: tools land in TC-A-02; the service still serves.
        log.info("phase1 tools not present: %s", safe_event(event="phase1_absent"))
    if args.transport == "stdio":
        mcp.run(transport="stdio", show_banner=False)
    else:
        asyncio.run(
            mcp.run_http_async(
                transport="streamable-http",
                host=args.host,
                port=args.port,
                path=args.path,
                show_banner=False,
            )
        )


if __name__ == "__main__":
    main()
