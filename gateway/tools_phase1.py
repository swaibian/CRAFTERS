"""Phase-1 tools: craft_apps, craft_status, craft_run, craft_run_tool, craft_app_call.

Contracts (per 08-REQUIRED-TOOLS.md Phase 1 + §B1/E2):

- ``craft_apps()`` — which apps exist, what each is for (registry metadata).
- ``craft_status(app?)`` — one call, all apps (omitted = every app): proxied
  backend state (documents/jobs/mode/roots/last_error).
- ``craft_run(app, command, params?, snapshot?)`` — guarded ``engine.execute``.
- ``craft_run_tool(app, tool, args?)`` — namespaced passthrough to any app's
  curated tools.
- ``craft_app_call(app, method, params?)`` — raw control-protocol escape hatch.

Every tool enforces the caller's allowlist (via the gateway ``AuthMiddleware``
— tools additionally re-check for direct-call safety), confines file params to
session roots, and logs ingress/egress through the project logger with params
redacted. Unknown app → ``BackendError`` surfaced as ``ToolError`` with a safe
message.

SW-REQ: SW-REQ-GW-CORE (Phase-1 tool surface, TC-A-02).
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from .auth import AuthStore, check_tool_allowed
from .backends import PILOT_APPS, BackendError, BackendManager, SessionRegistry
from .logger import get_logger, log_tool_ingress, safe_event
from .snapshots import SnapshotStore, is_destructive_command

log = get_logger()

# Pilot registry: app id → CLI command, default args, capability flags.
# Generic by design — the other 9 apps light up as registry entries with no
# code changes (TC-A-00 responsibility 3).
APP_REGISTRY: dict[str, dict[str, Any]] = {
    "photocraft": {
        "cli": "photocraft-cli",
        "args": ["mcp"],
        "description": "Raster photo editing (retouch, layers, filters).",
        "capabilities": ["render", "layers", "inspect"],
    },
    "pdfcraft": {
        "cli": "pdfcraft-cli",
        "args": ["mcp"],
        "description": "PDF documents (pages, render, text inspect).",
        "capabilities": ["render", "pages", "inspect"],
    },
    "gridcraft": {
        "cli": "gridcraft-cli",
        "args": ["mcp"],
        "description": "Structured data grids (sheets, cells, compute).",
        "capabilities": ["sheets", "inspect"],
    },
}

TOOL_NAMES = (
    "craft_apps",
    "craft_status",
    "craft_run",
    "craft_run_tool",
    "craft_app_call",
)


def _require_app(app: str) -> dict[str, Any]:
    """Return the registry entry for ``app`` or raise a safe ``ToolError``.

    :param app: App id.
    :raises ToolError: Unknown app (message names the app id only).
    """
    try:
        return APP_REGISTRY[app]
    except KeyError:
        raise ToolError(f"unknown app: {app}") from None


def _session_roots(
    sessions: SessionRegistry | None, session_id: str
) -> dict[str, str] | None:
    """Return ``{"read": ..., "write": ...}`` roots for status payloads."""
    if sessions is None:
        return None
    session = sessions.get(session_id)
    if session is None or not session.roots:
        return None
    first = str(session.roots[0])
    return {"read": first, "write": first}


class Phase1Tools:
    """Phase-1 tool implementations (auth + roots + backend wiring).

    :param backend_manager: Owns per-app backends (real or fake).
    :param sessions: Session registry for roots confinement.
    :param auth_store: Token registry for direct-call allowlist checks.
    :param snapshots: Snapshot store for the auto-snapshot policy hook
        (TC-B-01: before destructive ``craft_run`` calls). Shared with
        Phase-2 tools so ``craft_restore`` sees the same tokens.
    """

    def __init__(
        self,
        backend_manager: BackendManager,
        sessions: SessionRegistry | None = None,
        auth_store: AuthStore | None = None,
        snapshots: SnapshotStore | None = None,
    ) -> None:
        self._backends = backend_manager
        self._sessions = sessions
        self._auth = auth_store
        self._snapshots = snapshots

    def _check(
        self, tool: str, raw_token: str | None, user_id: str, session_id: str
    ) -> None:
        """Allowlist check + ingress log for direct (non-MCP) calls.

        :param tool: Tool name being invoked.
        :param raw_token: Presented bearer token (None skips the check —
            the MCP middleware already enforced it).
        :param user_id: Caller id for logging.
        :param session_id: Session id for logging.
        :raises ToolError: Allowlist denial (generic message).
        """
        log_tool_ingress(tool=tool, user_id=user_id, session_id=session_id, logger=log)
        if raw_token is not None and self._auth is not None:
            from .auth import AuthError

            try:
                check_tool_allowed(self._auth, raw_token, tool)
            except AuthError:
                raise ToolError("access denied") from None

    async def craft_apps(
        self,
        *,
        user_id: str = "local",
        session_id: str = "default",
        raw_token: str | None = None,
    ) -> dict[str, Any]:
        """List registered apps and what each is for.

        :param user_id: Caller id (logging only).
        :param session_id: Session id (logging only).
        :param raw_token: Bearer token for direct-call allowlist check.
        :returns: ``{"apps": [{app, description, cli, capabilities,
            available}]}``.
        """
        self._check("craft_apps", raw_token, user_id, session_id)
        apps = []
        for app_id, entry in APP_REGISTRY.items():
            try:
                backend = await self._backends.backend(app_id)
                status = await backend.status()
                available = status.available
            except BackendError:
                available = False
            apps.append(
                {
                    "app": app_id,
                    "description": entry["description"],
                    "cli": entry["cli"],
                    "capabilities": entry["capabilities"],
                    "available": available,
                }
            )
        log.info(
            "tool egress: %s",
            safe_event(
                event="tool_egress", tool="craft_apps", count=len(apps), ok=True
            ),
        )
        return {"apps": apps}

    async def craft_status(
        self,
        *,
        app: str | None = None,
        user_id: str = "local",
        session_id: str = "default",
        raw_token: str | None = None,
    ) -> dict[str, Any]:
        """One call, all apps (or one app): proxied state.

        :param app: App id, or None for every registered app.
        :param user_id: Caller id (logging only).
        :param session_id: Session id (roots reported from here).
        :param raw_token: Bearer token for direct-call allowlist check.
        :returns: ``{"apps": [{app, available, running, documents, jobs,
            mode, roots, last_error}]}``.
        """
        self._check("craft_status", raw_token, user_id, session_id)
        targets = [app] if app is not None else list(APP_REGISTRY)
        result = []
        for app_id in targets:
            _require_app(app_id)
            try:
                backend = await self._backends.backend(app_id)
                status = await backend.status()
                result.append(
                    {
                        "app": status.app,
                        "available": status.available,
                        "running": status.running,
                        "documents": status.documents,
                        "jobs": status.jobs,
                        "mode": status.mode,
                        "roots": _session_roots(self._sessions, session_id),
                        "last_error": status.last_error,
                    }
                )
            except BackendError as exc:
                result.append(
                    {
                        "app": app_id,
                        "available": False,
                        "running": "down",
                        "documents": [],
                        "jobs": [],
                        "mode": "headless",
                        "roots": _session_roots(self._sessions, session_id),
                        "last_error": str(exc),
                    }
                )
        log.info(
            "tool egress: %s",
            safe_event(
                event="tool_egress", tool="craft_status", count=len(result), ok=True
            ),
        )
        return {"apps": result}

    async def craft_run(
        self,
        *,
        app: str,
        command: str,
        params: dict[str, Any] | None = None,
        snapshot: bool = False,
        user_id: str = "local",
        session_id: str = "default",
        raw_token: str | None = None,
    ) -> dict[str, Any]:
        """Guarded ``engine.execute`` on an app.

        :param app: App id.
        :param command: Engine command name.
        :param params: Command params (redacted in logs; file paths confined
            to session roots when sessions are configured).
        :param snapshot: Snapshot-before-run flag (recorded; auto-taken when
            the auto-snapshot policy fires — destructive command or batch).
        :param user_id: Caller id (logging only).
        :param session_id: Session id for roots confinement.
        :param raw_token: Bearer token for direct-call allowlist check.
        :returns: Backend result payload (``snapshot_token`` included when a
            policy snapshot was taken).
        """
        self._check("craft_run", raw_token, user_id, session_id)
        _require_app(app)
        safe_params = self._confine_params(session_id, params or {})
        auto_token = await self._maybe_auto_snapshot(
            app, command, params or {}, snapshot, session_id, user_id
        )
        backend = await self._backend_or_raise(app)
        try:
            result = await backend.call_tool(
                "engine.execute",
                {"command": command, "params": safe_params, "snapshot": snapshot},
            )
        except BackendError as exc:
            raise ToolError(str(exc)) from None
        log.info(
            "tool egress: %s",
            safe_event(
                event="tool_egress", tool="craft_run", app=app, command=command, ok=True
            ),
        )
        payload = result if isinstance(result, dict) else {"result": result}
        if auto_token is not None:
            payload = {**payload, "snapshot_token": auto_token}
        return payload

    async def craft_run_tool(
        self,
        *,
        app: str,
        tool: str,
        args: dict[str, Any] | None = None,
        user_id: str = "local",
        session_id: str = "default",
        raw_token: str | None = None,
    ) -> dict[str, Any]:
        """Namespaced passthrough to any app's curated tools.

        :param app: App id.
        :param tool: Backend tool name.
        :param args: Tool args (redacted in logs; paths confined).
        :param user_id: Caller id (logging only).
        :param session_id: Session id for roots confinement.
        :param raw_token: Bearer token for direct-call allowlist check.
        :returns: Backend result payload.
        """
        self._check("craft_run_tool", raw_token, user_id, session_id)
        _require_app(app)
        safe_args = self._confine_params(session_id, args or {})
        backend = await self._backend_or_raise(app)
        try:
            result = await backend.call_tool(tool, safe_args)
        except BackendError as exc:
            raise ToolError(str(exc)) from None
        log.info(
            "tool egress: %s",
            safe_event(event="tool_egress", tool="craft_run_tool", app=app, ok=True),
        )
        return result if isinstance(result, dict) else {"result": result}

    async def craft_app_call(
        self,
        *,
        app: str,
        method: str,
        params: dict[str, Any] | None = None,
        user_id: str = "local",
        session_id: str = "default",
        raw_token: str | None = None,
    ) -> dict[str, Any]:
        """Raw control-protocol passthrough (escape hatch).

        :param app: App id.
        :param method: Control-protocol method (e.g. ``ui.inspect``).
        :param params: Method params (redacted in logs; paths confined).
        :param user_id: Caller id (logging only).
        :param session_id: Session id for roots confinement.
        :param raw_token: Bearer token for direct-call allowlist check.
        :returns: Backend result payload.
        """
        self._check("craft_app_call", raw_token, user_id, session_id)
        _require_app(app)
        safe_params = self._confine_params(session_id, params or {})
        backend = await self._backend_or_raise(app)
        try:
            result = await backend.call_tool(method, safe_params)
        except BackendError as exc:
            raise ToolError(str(exc)) from None
        log.info(
            "tool egress: %s",
            safe_event(
                event="tool_egress",
                tool="craft_app_call",
                app=app,
                method=method,
                ok=True,
            ),
        )
        return result if isinstance(result, dict) else {"result": result}

    async def _backend_or_raise(self, app: str):
        try:
            return await self._backends.backend(app)
        except BackendError as exc:
            raise ToolError(str(exc)) from None

    async def _maybe_auto_snapshot(
        self,
        app: str,
        command: str,
        params: dict[str, Any],
        snapshot: bool,
        session_id: str,
        user_id: str,
    ) -> str | None:
        """Auto-snapshot policy hook (TC-B-01, spec C1).

        Takes a snapshot before destructive ``craft_run`` calls: when the
        caller passes ``snapshot=True``, or when the policy predicate fires
        (destructive command stem or multi-destructive batch). The token is
        returned to the caller (``snapshot_token``); only its prefix is
        logged.

        :param app: App id.
        :param command: Engine command name.
        :param params: Raw command params (policy scan only).
        :param snapshot: Caller-requested snapshot flag.
        :param session_id: Owning session.
        :param user_id: Caller id (logging only).
        :returns: Snapshot token, or None when no snapshot was taken.
        """
        if self._snapshots is None:
            return None
        if not snapshot and not is_destructive_command(command, params):
            return None
        try:
            backend = await self._backends.backend(app)
            info = await backend.call_tool("doc_inspect", {})
        except BackendError:
            return None
        revision = int(info.get("revision", 0)) if isinstance(info, dict) else 0
        record = self._snapshots.create(
            session_id=session_id,
            app=app,
            revision=revision,
            user_id=user_id,
            label=f"auto:{command}",
            data_ref={"revision": revision},
        )
        log.info(
            "snapshot auto: %s",
            safe_event(
                event="snapshot_auto",
                tool="craft_run",
                app=app,
                command=command,
                session_id=session_id,
                user_id=user_id,
                revision=revision,
                ok=True,
            ),
        )
        return record.token

    def _confine_params(
        self, session_id: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Confine ``path``-like params to session roots; redact the rest.

        :param session_id: Session id whose roots apply.
        :param params: Raw params (never logged).
        :returns: Params with paths validated (as strings) — safe to forward.
        :raises ToolError: A path escapes the session roots.
        """
        if self._sessions is None:
            return dict(params)
        confined: dict[str, Any] = {}
        for key, value in params.items():
            if isinstance(value, str) and key.lower() in (
                "path",
                "output_path",
                "file",
                "filename",
            ):
                from .backends import RootsViolation

                try:
                    confined[key] = str(self._sessions.check_path(session_id, value))
                except RootsViolation:
                    raise ToolError("access denied") from None
            else:
                confined[key] = value
        return confined


def register_phase1_tools(
    mcp: FastMCP,
    *,
    backend_manager: BackendManager,
    sessions: SessionRegistry | None = None,
    auth_store: AuthStore | None = None,
    snapshots: SnapshotStore | None = None,
) -> Phase1Tools:
    """Wire the 5 Phase-1 tools into a gateway FastMCP app.

    :param mcp: Gateway app (from ``create_gateway``).
    :param backend_manager: App backend owner.
    :param sessions: Session registry for roots confinement.
    :param auth_store: Token registry (tools re-check for direct-call safety;
        the ``AuthMiddleware`` remains the primary enforcer).
    :param snapshots: Shared snapshot store for the auto-snapshot hook
        (share with ``register_phase2_tools``).
    :returns: The :class:`Phase1Tools` implementation (also stashed as
        ``mcp.phase1`` for tests/smoke).
    """
    impl = Phase1Tools(backend_manager, sessions, auth_store, snapshots)

    @mcp.tool(
        name="craft_apps",
        description="List registered Craft apps and what each is for.",
    )
    async def _craft_apps() -> dict[str, Any]:
        return await impl.craft_apps()

    @mcp.tool(
        name="craft_status",
        description="One call, all apps: proxied state (omit app for every app).",
    )
    async def _craft_status(app: str | None = None) -> dict[str, Any]:
        return await impl.craft_status(app=app)

    @mcp.tool(name="craft_run", description="Guarded engine.execute on an app.")
    async def _craft_run(
        app: str,
        command: str,
        params: dict[str, Any] | None = None,
        snapshot: bool = False,
    ) -> dict[str, Any]:
        return await impl.craft_run(
            app=app, command=command, params=params, snapshot=snapshot
        )

    @mcp.tool(
        name="craft_run_tool",
        description="Namespaced passthrough to any app's curated tools.",
    )
    async def _craft_run_tool(
        app: str, tool: str, args: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return await impl.craft_run_tool(app=app, tool=tool, args=args)

    @mcp.tool(
        name="craft_app_call",
        description="Raw control-protocol passthrough (escape hatch).",
    )
    async def _craft_app_call(
        app: str, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return await impl.craft_app_call(app=app, method=method, params=params)

    mcp.phase1 = impl  # type: ignore[attr-defined]
    log.info(
        "phase1 tools registered: %s",
        safe_event(event="phase1_registered", count=len(TOOL_NAMES)),
    )
    return impl


__all__ = [
    "APP_REGISTRY",
    "PILOT_APPS",
    "TOOL_NAMES",
    "Phase1Tools",
    "register_phase1_tools",
]
