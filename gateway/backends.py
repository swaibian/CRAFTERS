"""App CLI backends: spawn ``<app>-cli mcp`` subprocesses and proxy calls.

- :class:`SessionRegistry` — session id → roots/tokens/backend handles.
  :meth:`SessionRegistry.check_path` confines file access to the session's
  roots (escape attempts raise :class:`RootsViolation`). The check is lexical
  first, then a read-only symlink second opinion (``os.path.realpath``,
  never strict — missing parents degrade to the lexical verdict, never
  crash); every allow/deny decision is audited to the ``gateway.audit``
  logger with outside-roots paths redacted to parent only.
- :class:`AppBackend` — one live proxy per app: spawns the real CLI over
  stdio (FastMCP ``Client`` + ``StdioTransport``) or falls back to
  :class:`FakeAppBackend` when the CLI binary is absent, and exposes
  ``call_tool`` / ``list_tools`` / ``status``.
- :class:`BackendManager` — owns one backend per app id, shared across
  sessions; sessions only hold roots + token references (isolation is in the
  roots, not in duplicated processes).
- :class:`BridgeAppBackend` — Lane 3 bridge mode: drives a running desktop
  app over its loopback control channel (``gateway.bridge.BridgeClient``)
  with verbatim ``craft_app_call`` passthrough plus read-only aliases so
  the gateway's ``doc_inspect`` / ``render_preview`` probes keep working
  (``document.inspect`` or ``engine.execute document.inspect``;
  ``ui.screenshot`` hashed to ``source: bridge-window`` metadata).
- CLI path config — :func:`load_cli_paths` / :func:`resolve_cli_command`:
  per-app binary paths come from ``deploy/local-bin-paths.env`` (the Lane 1
  sync file, ``PHOTOCRAFT_CLI=/path/...`` one per line), overridden by
  ``CRAFTER_CLI_PATHS`` (a file path or inline ``K=V`` pairs) and finally by
  per-app ``<APP>_CLI`` env vars (highest precedence). A missing file
  degrades gracefully to ``PATH`` lookup. Real backends are the default;
  :class:`FakeAppBackend` is opt-in only (``use_fake=True`` explicit) or a
  loud per-app fallback when the binary is absent (warning log +
  ``craft_status`` ``mode:"fake"``).

SW-REQ: SW-REQ-GW-CORE (pilot app wiring + session roots, TC-A-01).
SW-REQ: SW-REQ-GW-VERIFY (containment hardening + audit, TC-B-02).
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .bridge import BridgeClient, BridgeConfig, BridgeError, summarize_screenshot
from .logger import get_audit_logger, get_logger, safe_event

log = get_logger()
audit_log = get_audit_logger()

PILOT_APPS = ("photocraft", "pdfcraft", "gridcraft")

#: Lane 1 sync file: absolute CLI paths, ``PHOTOCRAFT_CLI=/path/...`` one
#: per line. Resolved relative to the repo root (parent of ``gateway/``).
DEFAULT_BIN_PATHS_FILE = Path(__file__).resolve().parent.parent / "deploy" / "local-bin-paths.env"

#: Env var pointing at an alternate paths file, or holding inline ``K=V``
#: pairs (comma/newline separated) merged over the sync file.
CLI_PATHS_ENV = "CRAFTER_CLI_PATHS"


def cli_env_var(app: str) -> str:
    """Env var naming the CLI binary for ``app`` (``photocraft`` → ``PHOTOCRAFT_CLI``).

    :param app: App id.
    :returns: Env var name ``f"{app.upper()}_CLI"`` (dashes → underscores).
    """
    return f"{app.upper().replace('-', '_')}_CLI"


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse a ``KEY=value`` file (quotes stripped, ``#`` comments skipped).

    :param path: File to read; missing files yield ``{}`` (never raise).
    :returns: Mapping of keys to values.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    parsed: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            parsed[key] = value
    return parsed


def _parse_inline_pairs(text: str) -> dict[str, str]:
    """Parse inline ``K=V`` pairs separated by commas or newlines.

    :param text: Raw ``CRAFTER_CLI_PATHS`` value (not a file path).
    :returns: Mapping of keys to values.
    """
    parsed: dict[str, str] = {}
    for chunk in text.replace("\n", ",").split(","):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        key, _, value = chunk.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            parsed[key] = value
    return parsed


def load_cli_paths(
    env_file: str | Path | None = None,
    *,
    env: Any = os.environ,
) -> dict[str, str]:
    """Load per-app CLI binary paths (Lane 1 sync → env overrides).

    Precedence (lowest → highest): ``deploy/local-bin-paths.env`` (or
    ``env_file`` when given), ``CRAFTER_CLI_PATHS`` (existing file path, else
    inline ``K=V`` pairs), per-app ``<APP>_CLI`` env vars. A missing sync
    file is normal before Lane 1 lands and degrades to ``PATH`` lookup —
    never an error.

    :param env_file: Explicit paths file (defaults to the Lane 1 sync file).
    :param env: Environ mapping (injectable for tests).
    :returns: Mapping such as ``{"PHOTOCRAFT_CLI": "/path/to/photocraft-cli"}``.
    """
    merged: dict[str, str] = {}
    merged.update(_parse_env_file(Path(env_file) if env_file else DEFAULT_BIN_PATHS_FILE))
    override = env.get(CLI_PATHS_ENV, "") if hasattr(env, "get") else ""
    if override:
        candidate = Path(override)
        if candidate.is_file():
            merged.update(_parse_env_file(candidate))
        else:
            merged.update(_parse_inline_pairs(override))
    for app in PILOT_APPS:
        var = cli_env_var(app)
        value = env.get(var, "") if hasattr(env, "get") else ""
        if value:
            merged[var] = value
    return merged


def resolve_cli_command(
    app: str,
    cli_paths: dict[str, str] | None = None,
) -> list[str] | None:
    """Resolve the spawn command for ``app`` (``[<binary>, "mcp"]``).

    An explicit configured path wins when it names an existing executable;
    otherwise ``PATH`` lookup (``<app>-cli``) applies. A configured-but-dead
    path is treated as absent (logged, never fatal) so the caller can take
    the loud fake fallback.

    :param app: App id (binary ``f"{app}-cli"``).
    :param cli_paths: Mapping from :func:`load_cli_paths` (loaded fresh
        when omitted).
    :returns: Spawn argv, or None when no usable binary exists.
    """
    paths = cli_paths if cli_paths is not None else load_cli_paths()
    configured = paths.get(cli_env_var(app), "")
    if configured:
        candidate = Path(configured)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return [str(candidate), "mcp"]
        log.warning(
            "backend cli path unusable: %s",
            safe_event(event="backend_cli_path_dead", app=app),
        )
    found = shutil.which(f"{app}-cli")
    if found:
        return [found, "mcp"]
    return None


class RootsViolation(Exception):
    """A path escapes the session's filesystem roots (no details leak)."""


class BackendError(Exception):
    """App backend unavailable or call failed (safe message only)."""


@dataclass
class Session:
    """Per-session state: roots confine files, tokens scope auth.

    :param session_id: Unique session identifier.
    :param user_id: Owning user id.
    :param roots: Filesystem roots this session may touch (read+write).
    :param key_id: Non-secret token identifier bound to the session.
    """

    session_id: str
    user_id: str
    roots: list[Path] = field(default_factory=list)
    key_id: str = ""


class SessionRegistry:
    """Session id → roots/tokens/backend handles.

    :param default_roots: Roots assigned when a session is created without
        explicit roots.
    """

    def __init__(self, default_roots: list[Path] | None = None) -> None:
        self._sessions: dict[str, Session] = {}
        self._default_roots = [Path(r) for r in (default_roots or [])]

    def create(
        self,
        session_id: str,
        user_id: str,
        roots: list[str | Path] | None = None,
        key_id: str = "",
    ) -> Session:
        """Create (or replace) a session.

        :param session_id: Unique session identifier.
        :param user_id: Owning user id.
        :param roots: Filesystem roots; defaults to the registry defaults.
        :param key_id: Non-secret token identifier bound to the session.
        :returns: The new :class:`Session`.
        """
        resolved = [
            Path(r) for r in (roots if roots is not None else self._default_roots)
        ]
        session = Session(
            session_id=session_id, user_id=user_id, roots=resolved, key_id=key_id
        )
        self._sessions[session_id] = session
        log.info(
            "session created: %s",
            safe_event(event="session_create", session_id=session_id, user_id=user_id),
        )
        return session

    def get(self, session_id: str) -> Session | None:
        """Return the session, or ``None`` if unknown.

        :param session_id: Session identifier.
        """
        return self._sessions.get(session_id)

    def drop(self, session_id: str) -> bool:
        """Remove a session.

        :param session_id: Session identifier.
        :returns: True if a session was removed.
        """
        return self._sessions.pop(session_id, None) is not None

    def check_path(self, session_id: str, path: str | Path) -> Path:
        """Resolve ``path`` and confine it to the session's roots.

        Lexical resolution first (``..``/absolute/sibling-prefix rejected
        without touching the filesystem), then a read-only symlink second
        opinion: ``os.path.realpath`` (never strict — missing parents
        degrade to the lexical verdict) must also land inside a root.
        Every allow/deny decision is audited to the ``gateway.audit``
        logger; outside-roots paths are redacted to parent only.

        :param session_id: Session identifier (must exist).
        :param path: Candidate path (absolute or relative).
        :returns: Resolved absolute path inside one of the roots.
        :raises RootsViolation: Unknown session or path escapes all roots.
            The message names no filesystem locations.
        """
        session = self._sessions.get(session_id)
        if session is None:
            _audit_path_decision(session_id, ok=False, error_code="unknown_session")
            raise RootsViolation("unknown session")
        if not session.roots:
            _audit_path_decision(session_id, ok=False, error_code="no_roots")
            raise RootsViolation("no roots configured")
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = session.roots[0] / candidate
        resolved = _resolve_lexical(candidate)
        root_hit = _root_containing(session.roots, resolved)
        if root_hit is None:
            _audit_path_decision(session_id, ok=False, error_code="outside_roots")
            raise RootsViolation("path outside session roots")
        # Symlink second opinion (read-only, never strict): a symlink
        # inside the roots pointing outside must not pass. Missing
        # parents degrade to the lexical verdict (creation paths).
        real = Path(os.path.realpath(resolved))
        if _root_containing(session.roots, real) is None:
            _audit_path_decision(session_id, ok=False, error_code="symlink_escape")
            raise RootsViolation("path outside session roots")
        _audit_path_decision(session_id, ok=True)
        return resolved


def _resolve_lexical(path: Path) -> Path:
    """Lexically normalize a path without touching the filesystem."""
    anchor = path.anchor
    parts: list[str] = []
    for part in path.parts:
        if part == anchor or part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    if not parts:
        return Path(anchor or ".")
    return Path(anchor, *parts) if anchor else Path(*parts)


def _root_containing(roots: list[Path], resolved: Path) -> Path | None:
    """Return the first root containing ``resolved`` (itself or a parent).

    :param roots: Session roots (lexically normalized before compare).
    :param resolved: Already-resolved candidate path.
    :returns: The containing root, or None when outside every root.
    """
    for root in roots:
        root_resolved = _resolve_lexical(root)
        if resolved == root_resolved or root_resolved in resolved.parents:
            return root_resolved
    return None


def _audit_path_decision(session_id: str, *, ok: bool, error_code: str = "") -> None:
    """Audit one roots allow/deny decision (safe fields only, no paths).

    Paths outside the roots are never logged — not even the parent —
    because the parent of an escape attempt may itself be sensitive
    (e.g. ``/etc``). The decision carries session + outcome only.

    :param session_id: Session the decision applies to.
    :param ok: Whether the path was allowed.
    :param error_code: Machine-readable denial reason (no paths).
    """
    audit_log.info(
        "roots %s",
        safe_event(
            event="roots_decision",
            session_id=session_id,
            ok=ok,
            error_code=error_code,
        ),
    )


@dataclass
class AppStatus:
    """Point-in-time app health/state snapshot (safe fields only)."""

    app: str
    available: bool
    running: str
    documents: list[dict[str, Any]]
    jobs: list[dict[str, Any]]
    mode: str
    last_error: str | None = None


class FakeAppBackend:
    """In-process stand-in used when the real ``<app>-cli`` is absent.

    Implements the same ``call_tool`` / ``list_tools`` / ``status`` surface
    as :class:`AppBackend` with canned documents and jobs so the gateway,
    tools, and tests work without pilot CLIs. Never used when the
    real CLI binary is on ``PATH``. Shared live-agent tool names
    (``command_run``, ``command_list``, ``doc_save``, ``look``) answer with
    the canned shape of their shared-schema counterpart (``command_run``
    behaves as ``engine.execute``, ``look`` as ``render_preview``).

    :param app: App id (e.g. ``"photocraft"``).
    """

    TOOLS = (
        "doc_inspect",
        "engine.execute",
        "render_preview",
        "command_run",
        "command_list",
        "doc_save",
        "look",
    )

    def __init__(self, app: str) -> None:
        self.app = app
        self._revision = 1

    async def connect(self) -> None:
        """No-op (no subprocess to spawn)."""

    async def close(self) -> None:
        """No-op."""

    async def list_tools(self) -> list[str]:
        """Return the canned tool names."""
        return list(self.TOOLS)

    async def call_tool(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Handle a proxied call with canned responses.

        :param method: Backend method name.
        :param params: Already-validated params (content redacted by caller).
        :raises BackendError: Unknown method.
        """
        if method == "doc_inspect":
            return {
                "app": self.app,
                "revision": self._revision,
                "documents": [
                    {
                        "index": 0,
                        "path": "untitled",
                        "dirty": False,
                        "revision": self._revision,
                    }
                ],
            }
        if method in ("engine.execute", "command_run"):
            self._revision += 1
            return {"app": self.app, "ok": True, "revision": self._revision}
        if method == "command_list":
            return {"app": self.app, "commands": [{"id": "noop"}]}
        if method == "doc_save":
            return {"app": self.app, "ok": True, "path": params.get("path")}
        if method in ("render_preview", "look"):
            return {
                "app": self.app,
                "revision": self._revision,
                "content_hash": "sha256:fake",
            }
        raise BackendError(f"unknown method: {method}")

    async def status(self) -> AppStatus:
        """Return a canned healthy status."""
        return AppStatus(
            app=self.app,
            available=True,
            running="fake",
            documents=[
                {
                    "index": 0,
                    "path": "untitled",
                    "dirty": False,
                    "revision": self._revision,
                }
            ],
            jobs=[],
            mode="fake",
        )


class AppBackend:
    """Live proxy to one ``<app>-cli mcp`` subprocess over stdio.

    The binary resolves via :func:`resolve_cli_command` (Lane 1 sync file →
    env overrides → ``PATH``). Real backends are the default; fakes are
    never constructed here (see :class:`BackendManager` for the loud
    per-app fallback).

    :param app: App id; CLI binary is ``f"{app}-cli"`` invoked as
        ``<app>-cli mcp``.
    :param cli_paths: Mapping from :func:`load_cli_paths` (loaded fresh
        when omitted).
    """

    def __init__(self, app: str, cli_paths: dict[str, str] | None = None) -> None:
        self.app = app
        self._cli_paths = cli_paths
        self._client: Any = None
        self._lock = asyncio.Lock()
        self._available = False
        self._argv: list[str] | None = None

    @property
    def cli_name(self) -> str:
        """CLI binary name for this app (``<app>-cli``)."""
        return f"{self.app}-cli"

    @property
    def argv(self) -> list[str] | None:
        """Resolved spawn argv (set on successful :meth:`connect`)."""
        return self._argv

    async def connect(self) -> None:
        """Spawn the CLI subprocess (idempotent).

        :raises BackendError: CLI binary missing or spawn failed.
        """
        async with self._lock:
            if self._client is not None:
                return
            resolved = resolve_cli_command(
                self.app,
                self._cli_paths if self._cli_paths is not None else load_cli_paths(),
            )
            if resolved is None:
                raise BackendError(f"backend unavailable: {self.app}")
            from fastmcp import Client
            from fastmcp.client.transports import StdioTransport

            log.info(
                "backend spawn: %s",
                safe_event(
                    event="backend_spawn", app=self.app, command=f"{self.cli_name} mcp"
                ),
            )
            transport = StdioTransport(command=resolved[0], args=resolved[1:])
            self._client = Client(transport)
            await self._client.__aenter__()
            self._available = True
            self._argv = resolved

    async def close(self) -> None:
        """Shut down the subprocess (idempotent)."""
        async with self._lock:
            if self._client is not None:
                try:
                    await self._client.__aexit__(None, None, None)
                finally:
                    self._client = None
                    self._available = False

    async def list_tools(self) -> list[str]:
        """List tool names exposed by the app CLI."""
        if self._client is None:
            raise BackendError(f"backend not connected: {self.app}")
        tools = await self._client.list_tools()
        return [t.name for t in tools]

    async def call_tool(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Proxy one JSON-RPC tool call to the app CLI.

        :param method: Backend method name. Shared live-agent names reach
            the app MCP verbatim except ``look`` — the one name the app MCP
            spells differently (``doc_render_preview`` per the shared
            schema, docs/bridge-runbook.md §7).
        :param params: Validated params (never logged raw).
        :returns: Backend result payload.
        """
        if self._client is None:
            raise BackendError(f"backend not connected: {self.app}")
        if method == "look":
            method = "doc_render_preview"
        started = time.monotonic()
        try:
            result = await self._client.call_tool(method, dict(params))
        except Exception as exc:
            raise BackendError(f"backend call failed: {self.app}") from exc
        finally:
            duration_ms = int((time.monotonic() - started) * 1000)
            log.info(
                "backend proxy: %s",
                safe_event(
                    event="backend_proxy",
                    app=self.app,
                    method=method,
                    duration_ms=duration_ms,
                ),
            )
        return _tool_result_to_dict(result)

    async def status(self) -> AppStatus:
        """Return app health/state (degraded, never raising, on failure)."""
        try:
            if self._client is None:
                await self.connect()
            assert self._client is not None
            tools = await self.list_tools()
            _ = tools
            info: dict[str, Any] = {}
            try:
                info = await self.call_tool("doc_inspect", {})
            except BackendError:
                info = {}
            docs = info.get("documents", []) if isinstance(info, dict) else []
            return AppStatus(
                app=self.app,
                available=True,
                running="headless",
                documents=docs if isinstance(docs, list) else [],
                jobs=[],
                mode="headless",
            )
        except BackendError as exc:
            return AppStatus(
                app=self.app,
                available=False,
                running="down",
                documents=[],
                jobs=[],
                mode="headless",
                last_error=str(exc),
            )


#: Control methods advertised by :class:`BridgeAppBackend` (informational:
#: ``call_tool`` passes any method through verbatim, like ``control_call``).
BRIDGE_METHODS = (
    "engine.execute",
    "engine.commands",
    "document.inspect",
    "ui.inspect",
    "ui.screenshot",
    "ui.set",
    "ui.key",
    "ui.type",
    "ui.click",
    "ui.pointer",
    "ui.menu.invoke",
    "ui.menu.list",
    "ui.dialog.open",
    "ui.dialog.set",
    "ui.dialog.confirm",
    "ui.dialog.cancel",
    "ui.window.open",
    "ui.window.close",
    "ui.resize",
    "ui.focus",
    "app.open",
    "app.save",
    "jobs.list",
    "jobs.cancel",
)

#: Shared live-agent tool names (the schema the built-in chat agent uses over
#: the controller's direct control channel; table in docs/bridge-runbook.md
#: §7) → bridge vocabulary. Applied by :meth:`BridgeAppBackend.call_tool` so
#: ``craft_run_tool`` offers the same names on a live ``--control`` bridge.
#: ``doc_inspect`` needs no entry: it is already a gateway read alias there.
SHARED_TOOL_ALIASES = {
    "command_run": "engine.execute",
    "command_list": "engine.commands",
    "doc_save": "app.save",
    "look": "render_preview",
}


class BridgeAppBackend:
    """Lane 3 bridge proxy: drive a running desktop app over its loopback
    control channel instead of a headless CLI subprocess.

    :param config: Dial/auth parameters (:class:`BridgeConfig`).

    ``call_tool`` is a verbatim control-protocol passthrough (the
    ``craft_app_call`` escape hatch: ``{app, method, params}`` → one TCP
    JSON-lines call → reply), with the shared live-agent names mapped onto
    control methods per :data:`SHARED_TOOL_ALIASES` and two read-only
    aliases so the gateway's own probes keep working in bridge mode:

    - ``"doc_inspect"`` → ``document.inspect`` (``inspect_style="direct"``,
      gridcraft family) or ``engine.execute {"command":
      "document.inspect"}`` (``inspect_style="engine"``, photocraft family);
    - ``"render_preview"`` → ``ui.screenshot`` reduced to log-safe
      metadata (``content_hash`` over the real window pixels,
      ``source: "bridge-window"``) — so ``craft_look(scope="window")``
      provably differs from a headless render.
    """

    def __init__(self, config: BridgeConfig) -> None:
        self.app = config.app
        self._config = config
        self._client = BridgeClient(config)
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Dial the app's control channel (idempotent).

        :raises BackendError: App not listening or auth rejected. Never
            falls back — a bridge aimed at a live window must not silently
            edit a headless document instead (fail closed).
        """
        async with self._lock:
            if self._client.connected:
                return
            try:
                await self._client.connect()
            except BridgeError as exc:
                raise BackendError(str(exc)) from exc
            log.info(
                "backend bridge: %s",
                safe_event(
                    event="backend_bridge",
                    app=self.app,
                    host=self._config.host,
                    port=self._config.port,
                ),
            )

    async def close(self) -> None:
        """Close the control connection (idempotent)."""
        await self._client.close()

    async def list_tools(self) -> list[str]:
        """Return the bridgeable control-method vocabulary."""
        return list(BRIDGE_METHODS)

    async def call_tool(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Proxy one control call (verbatim passthrough + read aliases).

        :param method: Control-protocol method, shared live-agent tool name
            (mapped per :data:`SHARED_TOOL_ALIASES`), or ``doc_inspect`` /
            ``render_preview`` (gateway read aliases).
        :param params: Validated params (never logged raw).
        :returns: Reply payload (screenshot bytes reduced to metadata).
        :raises BackendError: Not connected or the app answered
            ``ok: false`` (message forwarded — it names the method/params
            problem, never secrets).
        """
        method = SHARED_TOOL_ALIASES.get(method, method)
        started = time.monotonic()
        try:
            if method == "render_preview":
                result = await self._screenshot(params)
            elif method == "doc_inspect":
                result = await self._inspect(params)
            else:
                try:
                    result = await self._client.call(method, dict(params))
                except BridgeError as exc:
                    raise BackendError(str(exc)) from exc
        finally:
            duration_ms = int((time.monotonic() - started) * 1000)
            log.info(
                "backend proxy: %s",
                safe_event(
                    event="backend_proxy",
                    app=self.app,
                    method=method,
                    duration_ms=duration_ms,
                ),
            )
        return result if isinstance(result, dict) else {"value": result}

    async def _inspect(self, params: dict[str, Any]) -> dict[str, Any]:
        """Map the gateway ``doc_inspect`` probe onto the control channel."""
        safe = {k: v for k, v in params.items() if k != "path"}
        try:
            if self._config.inspect_style == "engine":
                reply = await self._client.call(
                    "engine.execute",
                    {"command": "document.inspect", "params": safe},
                )
            else:
                reply = await self._client.call("document.inspect", safe)
        except BridgeError as exc:
            raise BackendError(str(exc)) from exc
        merged = {"app": self.app}
        if isinstance(reply, dict):
            merged.update(reply)
        return merged

    async def _screenshot(self, params: dict[str, Any]) -> dict[str, Any]:
        """Map the gateway ``render_preview`` probe onto ``ui.screenshot``.

        Only ``path`` (already roots-confined by the caller) is forwarded;
        the ``craft_look`` render knobs (scope/region/max_side/detail) have
        no control-protocol equivalent — the live window is the render.
        """
        shot_params: dict[str, Any] = {}
        if isinstance(params.get("path"), str):
            shot_params["path"] = params["path"]
        try:
            reply = await self._client.call("ui.screenshot", shot_params)
        except BridgeError as exc:
            raise BackendError(str(exc)) from exc
        if not isinstance(reply, dict):
            reply = {"value": reply}
        return summarize_screenshot(self.app, reply)

    async def status(self) -> AppStatus:
        """Return bridge health (degraded, never raising, on failure)."""
        try:
            await self.connect()
            info: dict[str, Any] = {}
            try:
                info = await self._client.call("ui.inspect", {})
            except BridgeError:
                info = {}
            _ = info
            return AppStatus(
                app=self.app,
                available=True,
                running="bridge",
                documents=[],
                jobs=[],
                mode="bridge",
            )
        except BackendError as exc:
            return AppStatus(
                app=self.app,
                available=False,
                running="down",
                documents=[],
                jobs=[],
                mode="bridge",
                last_error=str(exc),
            )


def _coerce_bridge_config(
    app: str, spec: BridgeConfig | str | dict[str, Any]
) -> BridgeConfig:
    """Normalize a bridge spec to :class:`BridgeConfig`.

    :param app: App id (used when the spec omits it).
    :param spec: Config, ``"host:port"`` string, or mapping with at least
        ``port`` (``host`` defaults to loopback).
    :raises BackendError: Malformed spec.
    """
    if isinstance(spec, BridgeConfig):
        return spec
    if isinstance(spec, str):
        host, _, port_s = spec.rpartition(":")
        if not host or not port_s.isdigit():
            raise BackendError(f"bad bridge endpoint for {app} (want host:port)")
        return BridgeConfig(app=app, host=host, port=int(port_s))
    if isinstance(spec, dict):
        try:
            return BridgeConfig(
                app=str(spec.get("app", app)),
                host=str(spec.get("host", "127.0.0.1")),
                port=int(spec.get("port", 7979)),
                token=spec.get("token"),
                token_file=spec.get("token_file"),
                inspect_style=str(spec.get("inspect_style", "direct")),
                timeout_s=float(spec.get("timeout_s", 55.0)),
            )
        except (TypeError, ValueError) as exc:
            raise BackendError(f"bad bridge config for {app}") from exc
    raise BackendError(f"bad bridge config for {app}")


def _tool_result_to_dict(result: Any) -> dict[str, Any]:
    """Best-effort conversion of an MCP call result to a plain dict."""
    if isinstance(result, dict):
        return result
    data = getattr(result, "data", None)
    if isinstance(data, dict):
        return data
    content = getattr(result, "content", None)
    if content:
        texts = [getattr(block, "text", "") for block in content]
        return {"content": [t for t in texts if t]}
    return {"ok": True}


class BackendManager:
    """Owns one backend per app id; sessions share backends, isolate roots.

    Real backends are the default. :class:`FakeAppBackend` is opt-in only:

    - ``use_fake=True`` (explicit) forces fakes for every app;
    - otherwise a missing/unspawnable CLI degrades **per app** to a fake
      with a loud ``WARNING`` (``backend_fake_fallback``) — and the fake's
      ``craft_status`` reports ``mode:"fake"`` so callers can tell.

    :param apps: App ids to manage (defaults to :data:`PILOT_APPS`).
    :param use_fake: Force :class:`FakeAppBackend` even when real CLIs exist
        (tests and environments without pilot CLIs). Must be passed
        explicitly — the silent auto-fake default is gone.
    :param cli_paths: Mapping from :func:`load_cli_paths` (loaded fresh
        when omitted, so a late-landing Lane 1 sync file is picked up by
        new managers).
    :param bridges: Optional app id → bridge spec (:class:`BridgeConfig`,
        ``"host:port"`` string, or mapping) for Lane 3 bridge mode. A
        configured bridge wins over the CLI subprocess for that app (unless
        ``use_fake`` is forced) and is fail-closed: a down app raises
        instead of degrading to a fake, so a bridge aimed at a live window
        can never silently edit a headless document.
    """

    def __init__(
        self,
        apps: Sequence[str] = PILOT_APPS,
        *,
        use_fake: bool = False,
        cli_paths: dict[str, str] | None = None,
        bridges: dict[str, BridgeConfig | str | dict[str, Any]] | None = None,
    ) -> None:
        self._apps = tuple(apps)
        self._force_fake = use_fake
        self._cli_paths = cli_paths if cli_paths is not None else load_cli_paths()
        self._bridges: dict[str, BridgeConfig] = {
            app: _coerce_bridge_config(app, spec) for app, spec in (bridges or {}).items()
        }
        self._backends: dict[str, AppBackend | FakeAppBackend | BridgeAppBackend] = {}
        self._fake_fallback: set[str] = set()
        self._lock = asyncio.Lock()

    @property
    def use_fake(self) -> bool:
        """Whether fake backends were explicitly forced (never auto-set)."""
        return self._force_fake

    @property
    def fake_fallback_apps(self) -> frozenset[str]:
        """Apps currently served by the loud missing-binary fake fallback."""
        return frozenset(self._fake_fallback)

    def is_fake(self, app: str) -> bool:
        """Whether ``app`` is currently served by a fake backend.

        :param app: App id.
        """
        backend = self._backends.get(app)
        return isinstance(backend, FakeAppBackend)

    def is_bridge(self, app: str) -> bool:
        """Whether ``app`` is currently served by a bridge backend.

        :param app: App id.
        """
        return isinstance(self._backends.get(app), BridgeAppBackend)

    @property
    def apps(self) -> tuple[str, ...]:
        """Managed app ids."""
        return self._apps

    async def backend(
        self, app: str
    ) -> AppBackend | FakeAppBackend | BridgeAppBackend:
        """Return the (connected) backend for ``app`` (real by default).

        :param app: App id; must be managed.
        :raises BackendError: Unknown app, or bridge app down (fail closed —
            bridges never degrade to fakes).
        """
        if app not in self._apps:
            raise BackendError(f"unknown app: {app}")
        async with self._lock:
            existing = self._backends.get(app)
            if existing is not None:
                return existing
            created: AppBackend | FakeAppBackend | BridgeAppBackend
            if self._force_fake:
                created = FakeAppBackend(app)
                await created.connect()
            elif app in self._bridges:
                bridge = BridgeAppBackend(self._bridges[app])
                await bridge.connect()  # raises on down app: fail closed
                created = bridge
            else:
                real = AppBackend(app, cli_paths=self._cli_paths)
                try:
                    await real.connect()
                except BackendError:
                    # Loud fallback: fake serves traffic, but nobody can
                    # mistake it for real (warning log + mode:"fake" status).
                    log.warning(
                        "backend fake fallback: %s",
                        safe_event(
                            event="backend_fake_fallback",
                            app=app,
                            error_code="binary_missing",
                        ),
                    )
                    created = FakeAppBackend(app)
                    await created.connect()
                    self._fake_fallback.add(app)
                    self._backends[app] = created
                    return created
                created = real
            self._backends[app] = created
            return created

    async def close_all(self) -> None:
        """Shut down every spawned backend."""
        async with self._lock:
            for backend in self._backends.values():
                try:
                    await backend.close()
                except Exception:  # noqa: BLE001 — shutdown must not raise
                    logging.getLogger("gateway").warning(
                        "backend close failed: %s",
                        safe_event(event="backend_close", app=backend.app, ok=False),
                    )
            self._backends.clear()
