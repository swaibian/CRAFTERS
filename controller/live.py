"""Live desktop apps as chat objects (Lane 3, controller side).

The controller's chat loop works on local working copies
(:mod:`controller.documents`). This module bridges the remaining gap to a
*running* Craft desktop app started with ``--control``: it dials the app's
loopback control channel (reusing :mod:`gateway.bridge`), lists the
documents open in the live window, and captures the window pixels so the
user can attach them as the chat object.

V1 model (import, read-first): attaching snapshots the live window via
``ui.screenshot`` into the session work dir and registers it as a normal
photo document with ``source="live"`` provenance. Chat, thumbnail,
download, and snapshot/restore then work unchanged on the attached copy.

Live editing lane: :class:`LiveExecutor` drives the linked document in the
user's OPEN window through the app's own command surface
(``engine.execute`` / ``engine.commands`` / ``app.save``) so agent edits
are immediately visible in the live app. The imported copy is never
mutated in this lane, and the user's file is only written when the agent
explicitly calls ``doc_save`` (``app.save`` — ``file.save`` is refused by
the control channel). When the bridge is down the lane fails honestly
("app is not running") instead of falling back to the copy.

Config: per-app ``CRAFTER_BRIDGE_<APP>=host:port`` plus optional
``CRAFTER_BRIDGE_<APP>_TOKEN_FILE`` (photocraft-style bearer token),
parsed per app with fault isolation (one malformed var must not take down
the others). Only loopback dial targets are allowed (enforced by
:class:`gateway.bridge.BridgeClient`).

SW-REQ: SW-REQ-STREAM (live-app chat objects, controller side).
"""

from __future__ import annotations

import asyncio
import base64
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from gateway.bridge import BridgeClient, BridgeConfig, BridgeError

from .logger import get_logger, safe_event

log = get_logger()

#: Apps the live picker offers (pdfcraft has no TCP control channel — it
#: reports ``down`` with a file-based hint instead of a dial attempt).
LIVE_APPS = ("photocraft", "gridcraft", "pdfcraft")

#: Exact start commands shown when an app is down (copy-pasteable).
START_HINTS = {
    "photocraft": (
        "photocraft --control 7878 "
        "--control-token-file /tmp/pc.token "
        "--automation-read-root /work --automation-write-root /work"
    ),
    "gridcraft": "gridcraft --control 7979",
    "pdfcraft": (
        "pdfcraft --control ~/.pdfcraft-control.json "
        "(file-based control — no TCP port; attach is unavailable, "
        "drop the PDF file instead)"
    ),
}

#: Apps the Launch button may start (TCP control channel only — pdfcraft's
#: file-based control has nothing to dial, so it stays manual).
LAUNCHABLE_APPS = ("photocraft", "gridcraft")

#: Control ports the launched apps listen on (mirrors START_HINTS).
LAUNCH_PORTS = {"photocraft": 7878, "gridcraft": 7979}

#: How long to wait for the control channel after spawn before giving up
#: (first GUI start on a cold machine is slow; the app keeps starting in
#: the background and Refresh picks it up later).
LAUNCH_TIMEOUT_S = 45.0

#: Reply keys searched first for screenshot payloads (base64 PNG), mirroring
#: ``gateway.bridge.summarize_screenshot`` without importing its metadata
#: shape (here the raw bytes are needed, and they never leave this module
#: except into the session work dir).
_SCREENSHOT_KEYS = ("base64", "image", "png", "data", "screenshot")

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

#: Windows drive/stream prefix (``C:``/``c:``) refused for automation paths.
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


class LiveError(Exception):
    """Live-app failure (down, auth, protocol — safe message only)."""


@dataclass
class LiveDocument:
    """One document open in a live desktop window.

    :param index: Engine document index (``document.activate`` target).
    :param name: Display name from the live session.
    :param width: Document width in pixels (when reported).
    :param height: Document height in pixels (when reported).
    :param dirty: Unsaved-changes flag (when reported).
    :param active: Whether this is the window's active document.
    """

    index: int
    name: str
    width: int | None = None
    height: int | None = None
    dirty: bool = False
    active: bool = False


@dataclass
class LiveStatus:
    """Point-in-time reachability of one desktop app.

    :param app: App id.
    :param running: Whether the control channel answered.
    :param mode: ``"bridge"`` when live, ``"down"`` otherwise.
    :param last_error: Safe failure reason (None when running).
    :param hint: Exact ``--control`` start command (when down).
    """

    app: str
    running: bool
    mode: str
    last_error: str | None = None
    hint: str = ""


def live_configs_from_env(
    apps: tuple[str, ...] = LIVE_APPS,
    *,
    env: Any = os.environ,
) -> dict[str, BridgeConfig]:
    """Build bridge configs, one malformed var at a time (fault-isolated).

    Same ``CRAFTER_BRIDGE_<APP>=host:port`` + ``CRAFTER_BRIDGE_<APP>_TOKEN_FILE``
    convention as :func:`gateway.bridge.bridges_from_env`, but each app is
    parsed independently so one malformed var cannot hide the healthy apps.
    Pdfcraft is skipped: it has no TCP control channel (file-based), so
    there is nothing to dial.

    :param apps: App ids to probe for.
    :param env: Environ mapping (injectable for tests).
    :returns: App id → :class:`BridgeConfig` for every well-formed var.
    """
    get = env.get if hasattr(env, "get") else (lambda _k, _d="": _d)
    configs: dict[str, BridgeConfig] = {}
    for app in apps:
        if app == "pdfcraft":
            continue
        endpoint = get(f"CRAFTER_BRIDGE_{app.upper()}", "")
        if not endpoint:
            continue
        host, _, port_s = str(endpoint).rpartition(":")
        if not host or not str(port_s).isdigit():
            log.warning(
                "live bridge config skipped: %s",
                safe_event(event="live_config_skip", app=app, ok=False),
            )
            continue
        token_file = get(f"CRAFTER_BRIDGE_{app.upper()}_TOKEN_FILE") or None
        configs[app] = BridgeConfig(
            app=app,
            host=host,
            port=int(port_s),
            token_file=token_file,
            inspect_style="engine" if app == "photocraft" else "direct",
        )
    return configs


@dataclass
class LiveManager:
    """Request-scoped driver for live desktop apps (no idle connections).

    A fresh :class:`BridgeClient` is dialled per call and closed before
    returning — the desktop closes idle connections after ~30 s anyway, so
    holding one open buys nothing and leaks on shutdown.

    :param bridges: App id → :class:`BridgeConfig` (loopback only).
    :param roots: App id → automation write root recorded at launch
        (:func:`launch_app`). :meth:`screenshot_png` saves its capture
        inside the root because the app's write authority is confined
        there — a system-temp path would be rejected.
    """

    bridges: dict[str, BridgeConfig] = field(default_factory=dict)
    roots: dict[str, str] = field(default_factory=dict)

    async def status(self, app: str) -> LiveStatus:
        """Probe one app's control channel (never raises).

        :param app: App id.
        :returns: :class:`LiveStatus` (``mode`` ``"bridge"`` or ``"down"``).
        """
        config = self.bridges.get(app)
        if config is None:
            return LiveStatus(
                app=app,
                running=False,
                mode="down",
                last_error="not configured",
                hint=START_HINTS.get(app, ""),
            )
        client = BridgeClient(config)
        try:
            await client.connect()
            try:
                await client.call("ui.inspect", {})
            except BridgeError:
                pass  # connect succeeding is enough for "running"
            return LiveStatus(app=app, running=True, mode="bridge")
        except BridgeError as exc:
            return LiveStatus(
                app=app,
                running=False,
                mode="down",
                last_error=str(exc),
                hint=START_HINTS.get(app, ""),
            )
        finally:
            await client.close()

    async def list_documents(self, app: str) -> tuple[list[LiveDocument], int | None]:
        """List the documents open in the live window.

        Photocraft shape (verified against
        ``crates/engine/src/inspect.rs`` + ``crates/ui-egui/src/control.rs``):
        ``ui.inspect`` → ``{session: {active, documents: [{index, name,
        width, height, dirty}]}}``. Unknown shapes degrade: the active
        ``document`` object (when present) becomes a single-entry list;
        otherwise :class:`LiveError`.

        :param app: App id (must be configured).
        :returns: ``(documents, active_index)``.
        :raises LiveError: Not configured, app down, auth rejected, or no
            document info in the reply.
        """
        reply = await self._call(app, "ui.inspect", {})
        session = reply.get("session") if isinstance(reply, dict) else None
        documents: list[LiveDocument] = []
        active: int | None = None
        if isinstance(session, dict):
            raw_docs = session.get("documents")
            if isinstance(raw_docs, list):
                for entry in raw_docs:
                    if not isinstance(entry, dict):
                        continue
                    try:
                        index = int(entry.get("index", len(documents)))
                    except (TypeError, ValueError):
                        continue
                    documents.append(
                        LiveDocument(
                            index=index,
                            name=str(entry.get("name", f"document {index}")),
                            width=_optional_int(entry.get("width")),
                            height=_optional_int(entry.get("height")),
                            dirty=bool(entry.get("dirty", False)),
                        )
                    )
            raw_active = session.get("active")
            if isinstance(raw_active, int):
                active = raw_active
        if (
            not documents
            and isinstance(reply, dict)
            and isinstance(reply.get("document"), dict)
        ):
            active_doc = reply["document"]
            documents.append(
                LiveDocument(
                    index=0,
                    name=str(active_doc.get("name", "untitled")),
                    width=_optional_int(active_doc.get("width")),
                    height=_optional_int(active_doc.get("height")),
                )
            )
            active = 0
        if not documents:
            raise LiveError("live window reports no open documents")
        for doc in documents:
            doc.active = active is not None and doc.index == active
        log.info(
            "live documents listed: %s",
            safe_event(event="live_list", app=app, count=len(documents), ok=True),
        )
        return documents, active

    async def screenshot_png(self, app: str, *, document: int | None = None) -> bytes:
        """Capture the live window as PNG bytes (``ui.screenshot``).

        When ``document`` names a non-active document index, the window is
        switched to it first via ``engine.execute {document.activate}``
        (photocraft style) so the capture shows the selected document.

        File-first: the capture is saved to ``{"path": ...}`` inside the
        app's automation write root (recorded at launch; system temp
        otherwise) and read back locally — a full-window base64 reply
        blows past the 8 MiB control-channel ceiling (that was a live
        500). Base64 remains the fallback for small windows and older
        replies.

        :param app: App id (must be configured).
        :param document: Engine document index to activate first (None =
            keep the active document).
        :returns: Raw PNG bytes (never logged).
        :raises LiveError: App down, no image in the reply, or the window
            is occluded (macOS stops rendering hidden windows — focus it).
        """
        if document is not None:
            docs, active = await self.list_documents(app)
            if all(doc.index != document for doc in docs):
                raise LiveError(f"unknown live document: {document}")
            if active is None or document != active:
                await self._call(
                    app,
                    "engine.execute",
                    {"command": "document.activate", "params": {"document": document}},
                )
        shot_dir = self.roots.get(app) or tempfile.gettempdir()
        fd, shot_path = tempfile.mkstemp(
            prefix=f"crafter-shot-{app}-", suffix=".png", dir=shot_dir
        )
        os.close(fd)
        png: bytes | None = None
        reply: dict[str, Any] = {}
        try:
            try:
                reply = await self._call(app, "ui.screenshot", {"path": shot_path})
                png = _read_png_file(shot_path)
            except LiveError:
                # Rejected path (unknown roots, read-only dir) or an app
                # without file output — fall through to base64 below.
                png = None
            if png is None and not reply:
                reply = await self._call(app, "ui.screenshot", {})
            if png is None:
                png = _extract_png_bytes(reply)
        finally:
            try:
                os.unlink(shot_path)
            except OSError:
                pass
        if png is None:
            raise LiveError("could not capture the live window (is it occluded?)")
        log.info(
            "live screenshot captured: %s",
            safe_event(event="live_capture", app=app, ok=True),
        )
        return png

    async def _call(
        self, app: str, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """One authenticated control call (connect → call → close).

        :param app: App id (must be configured).
        :param method: Control-protocol method.
        :param params: Method params.
        :returns: The reply's ``result`` payload.
        :raises LiveError: Not configured or any channel failure.
        """
        config = self.bridges.get(app)
        if config is None:
            raise LiveError(f"{app} is not running ({START_HINTS.get(app, '')})")
        client = BridgeClient(config)
        try:
            try:
                await client.connect()
            except BridgeError as exc:
                raise LiveError(f"cannot reach {app} ({exc})") from exc
            try:
                result = await client.call(method, params)
            except BridgeError as exc:
                raise LiveError(str(exc)) from exc
            return result if isinstance(result, dict) else {"value": result}
        finally:
            await client.close()


@dataclass
class LiveExecutor:
    """Drive one linked live document through its app's command surface.

    The agent loop's live lane: every tool call runs a real command in the
    user's OPEN desktop window (``engine.execute``) so the effect is
    immediately visible there. The linked engine document is activated
    before each command (``document.activate``, same pattern as
    :meth:`LiveManager.screenshot_png`). Nothing is written to the user's
    file unless :meth:`save` is called — ``app.save`` is the only allowed
    write (``file.save`` is refused by the control channel; see the app's
    ``docs/control-protocol.md``).

    :param manager: Live manager holding the app's bridge config + write root.
    :param app: App id (e.g. ``"photocraft"``).
    :param document: Linked engine document index (activated before every
        command; None = leave the window's active document alone).
    """

    manager: LiveManager
    app: str
    document: int | None = None

    async def execute(
        self, command: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Run one command id on the linked document (activate-first).

        :param command: Engine/UI command id (e.g. ``image.imageRotationcw``,
            ``document.inspect``).
        :param params: Command params object (``{}`` when none).
        :returns: The command's result payload.
        :raises LiveError: Empty command id, app down, or the app refused
            the command (app error text truncated; never params/pixels).
        """
        if not str(command).strip():
            raise LiveError("command_run needs a command id")
        if self.document is not None:
            await self._invoke(
                "engine.execute",
                {
                    "command": "document.activate",
                    "params": {"document": self.document},
                },
            )
        return await self._invoke(
            "engine.execute", {"command": command, "params": params or {}}
        )

    async def commands(self, filter: str | None = None) -> dict[str, Any]:
        """List the app's command registry with params docs + enablement.

        :param filter: Optional substring filter (None = whole registry).
        :returns: The ``engine.commands`` result payload.
        :raises LiveError: App down or the call failed.
        """
        params = {"filter": filter} if filter else {}
        return await self._invoke("engine.commands", params)

    async def inspect(self) -> dict[str, Any]:
        """Inspect the linked document (layer tree, history, dims).

        Runs ``document.inspect`` through ``engine.execute`` — the desktop
        control channel's safe path (the ``doc.inspect`` method is the
        headless-server spelling of the same JSON).

        :returns: The inspection payload (``width``, ``height``, ``layers``,
            ``history``, ...).
        :raises LiveError: App down or the call failed.
        """
        return await self.execute("document.inspect")

    async def save(self, path: str | None = None) -> dict[str, Any]:
        """Save the linked document via ``app.save`` (write-root confined).

        Without ``path`` the app writes back to the document's own file
        (like File › Save). A ``path`` must be a relative forward-slash
        path under the app's automation write root — absolute paths,
        ``~``, backslashes and ``..`` traversal are refused locally before
        the round trip (mirroring the app's automation containment).

        :param path: Optional relative target path.
        :returns: The ``app.save`` result payload (``path`` written,
            ``warnings``).
        :raises LiveError: Path escapes the write root, app down, or the
            app refused the save.
        """
        params = {"path": _confine_write_path(path)} if path is not None else {}
        return await self._invoke("app.save", params)

    async def look(self) -> bytes:
        """Capture the live window as PNG bytes (never logged).

        :returns: Raw PNG bytes.
        :raises LiveError: App down or the window could not be captured.
        """
        try:
            return await self.manager.screenshot_png(self.app, document=self.document)
        except LiveError as exc:
            error = _channel_error(self.app, "look", exc)
            log.warning(
                "live call failed: %s",
                safe_event(event="live_call", app=self.app, error=str(error), ok=False),
            )
            raise error from exc

    async def _invoke(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """One authenticated control call on the linked app.

        :param method: Control-protocol method.
        :param params: Method params.
        :returns: The reply's ``result`` payload.
        :raises LiveError: Honest failure (app down vs. method error).
        """
        try:
            return await self.manager._call(self.app, method, params)
        except LiveError as exc:
            error = _channel_error(self.app, method, exc)
            log.warning(
                "live call failed: %s",
                safe_event(event="live_call", app=self.app, error=str(error), ok=False),
            )
            raise error from exc


def live_manager_from_env() -> LiveManager:
    """Build a :class:`LiveManager` from the process environment.

    :returns: Manager with every well-formed ``CRAFTER_BRIDGE_<APP>`` entry
        (possibly none — all apps then report ``down`` with hints).
    """
    return LiveManager(bridges=live_configs_from_env())


def resolve_desktop_binary(app: str, *, env: Any = os.environ) -> str | None:
    """Locate a launchable desktop GUI binary (never raises).

    Precedence: ``CRAFTER_DESKTOP_<APP>`` (explicit path, must be
    executable) → ``<app>`` on ``PATH`` (``shutil.which`` resolves
    ``.exe`` via ``PATHEXT`` on Windows). Anything else (unknown app,
    missing binary) resolves to None so the caller can report the hint.

    :param app: App id.
    :param env: Environ mapping (injectable for tests).
    :returns: Absolute binary path, or None when unavailable.
    """
    if app not in LAUNCHABLE_APPS:
        return None
    get = env.get if hasattr(env, "get") else (lambda _k, _d="": _d)
    explicit = str(get(f"CRAFTER_DESKTOP_{app.upper()}", "") or "")
    if explicit:
        if os.path.isfile(explicit) and os.access(explicit, os.X_OK):
            return explicit
        return None
    found = shutil.which(app)
    return found if found else None


def desktop_launch_argv(app: str, *, token_file: str, work_root: str) -> list[str]:
    """Fixed spawn argv for one launchable app (no user input anywhere).

    :param app: App id (must be in :data:`LAUNCHABLE_APPS`).
    :param token_file: Bearer-token file for photocraft (0600, written by
        the caller — the token travels via file, never on the command line
        and never into logs).
    :param work_root: Automation read/write root for photocraft.
    :returns: ``[binary, ...fixed flags...]`` (binary resolved separately).
    :raises LiveError: App is not launchable.
    """
    if app == "photocraft":
        return [
            "--control",
            str(LAUNCH_PORTS["photocraft"]),
            "--control-token-file",
            token_file,
            "--automation-read-root",
            work_root,
            "--automation-write-root",
            work_root,
        ]
    if app == "gridcraft":
        return ["--control", str(LAUNCH_PORTS["gridcraft"])]
    raise LiveError(f"{app} cannot be launched (no TCP control channel)")


def _detached_kwargs() -> dict[str, Any]:
    """Platform-appropriate "outlive the server" spawn flags.

    POSIX (macOS/Linux): ``start_new_session=True`` (``setsid`` — the
    window survives controller restarts; ``start_new_session`` is not
    accepted on Windows). Windows: ``DETACHED_PROCESS |
    CREATE_NEW_PROCESS_GROUP`` (no console window, Ctrl+C of the server
    does not reach the app).

    :returns: Extra :func:`subprocess.Popen` kwargs for this platform.
    """
    if sys.platform == "win32":
        return {
            "creationflags": getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        }
    return {"start_new_session": True}


def _spawn_detached(
    argv: list[str], log_path: str, *, spawn: Callable[..., Any]
) -> Any:
    """Spawn a desktop app detached, logging to ``log_path`` (sync helper).

    Kept out of the async path so the event loop never blocks on file
    IO — :func:`launch_app` stays a thin async wrapper around it.

    :param argv: Fixed spawn argv (binary + flags, no user input).
    :param log_path: Stdout/stderr capture file (appended).
    :param spawn: Process factory.
    :returns: The process object (``.pid`` read by the caller).
    :raises LiveError: Log file or spawn failed (safe message only).
    """
    try:
        with open(log_path, "ab") as log_handle:
            return spawn(
                argv,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                **_detached_kwargs(),
            )
    except OSError as exc:
        raise LiveError(f"could not start {argv[0] if argv else '?'} ({exc})") from None


async def launch_app(
    manager: LiveManager,
    app: str,
    *,
    env: Any = os.environ,
    spawn: Callable[..., Any] | None = None,
    timeout_s: float = LAUNCH_TIMEOUT_S,
) -> dict[str, Any]:
    """Start a down desktop app and wait for its control channel.

    Idempotent: an already-running app returns immediately without a
    spawn. Otherwise the allowlisted binary is started detached
    (``start_new_session``, logs to ``<work_root>/crafter-<app>.log``),
    its bridge config is registered on ``manager`` so status flips to
    running without a restart, and the channel is polled until it
    answers or ``timeout_s`` elapses (the app keeps starting in the
    background — Refresh picks it up).

    Platform notes (ArtCraft ships on all three — the same call works):
    macOS/Linux detach via ``setsid``; Windows via ``DETACHED_PROCESS |
    CREATE_NEW_PROCESS_GROUP`` (no console window). The child inherits
    the server environment, so on Linux it needs ``DISPLAY``/``X11``
    (or Xvfb/offscreen) and on macOS a logged-in Aqua session — a
    headless daemon/SSH session without a display cannot show a window
    (the call then times out honestly instead of failing loudly).
    ``shutil.which`` resolves ``.exe`` via ``PATHEXT`` on Windows.

    :param manager: Live manager (mutated: bridge config registered).
    :param app: App id.
    :param env: Environ mapping (injectable for tests).
    :param spawn: Process factory (``None`` = :func:`subprocess.Popen`;
        resolved at call time so tests can patch it).
    :param timeout_s: Max seconds to wait for the channel.
    :returns: ``{app, running, mode, pid}``.
    :raises LiveError: Not launchable, binary missing, spawn failed, or
        the channel stayed down past the timeout (safe message + hint in
        the service layer).
    """
    if spawn is None:
        spawn = subprocess.Popen
    if app not in LAUNCHABLE_APPS:
        raise LiveError(f"{app} cannot be launched (no TCP control channel)")
    state = await manager.status(app)
    if state.running:
        return {"app": app, "running": True, "mode": state.mode, "pid": None}
    binary = resolve_desktop_binary(app, env=env)
    if binary is None:
        raise LiveError(
            f"{app} desktop binary not found "
            f"(set CRAFTER_DESKTOP_{app.upper()} or put {app} on PATH)"
        )
    get = env.get if hasattr(env, "get") else (lambda _k, _d="": _d)
    work_root = str(get("CRAFTER_DESKTOP_ROOT", "") or "") or str(
        os.path.join(os.path.expanduser("~"), "CraftFiles")
    )
    os.makedirs(work_root, exist_ok=True)
    token_file = ""
    if app == "photocraft":
        fd, token_file = tempfile.mkstemp(prefix=f"crafter-{app}-", suffix=".token")
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)
            # Else (Windows): no POSIX perms — the per-user temp dir ACL
            # is the protection; the token never hits logs either way.
            with os.fdopen(fd, "w") as handle:
                handle.write(secrets.token_hex(32))
        except OSError:
            try:
                os.close(fd)
            except OSError:
                pass
            raise LiveError(f"could not write {app} token file") from None
    argv = [
        binary,
        *desktop_launch_argv(app, token_file=token_file, work_root=work_root),
    ]
    log_path = os.path.join(work_root, f"crafter-{app}.log")
    proc = _spawn_detached(argv, log_path, spawn=spawn)
    pid = getattr(proc, "pid", None)
    port = LAUNCH_PORTS[app]
    manager.bridges[app] = BridgeConfig(
        app=app,
        host="127.0.0.1",
        port=port,
        token_file=token_file or None,
        inspect_style="engine" if app == "photocraft" else "direct",
    )
    # Screenshot captures must land inside the automation write root.
    manager.roots[app] = work_root
    log.info(
        "live app launched: %s",
        safe_event(event="live_launch", app=app, ok=True, pid=pid, port=port),
    )
    waited = 0.0
    step = 1.0
    while waited < timeout_s:
        await asyncio.sleep(step)
        waited += step
        if (await manager.status(app)).running:
            return {"app": app, "running": True, "mode": "bridge", "pid": pid}
    raise LiveError(
        f"{app} is still starting (control channel silent after {timeout_s:g}s — "
        "hit Refresh to retry)"
    )


def sanitize_filename(name: str) -> str:
    """Make a live document name safe for the session work dir.

    :param name: Live document name (arbitrary user text).
    :returns: Filesystem-safe stem (non-word chars → ``_``, capped at 40).
    """
    stem = re.sub(r"[^\w.-]+", "_", name).strip("._") or "live"
    return stem[:40]


def _confine_write_path(path: str) -> str:
    """Validate a ``doc_save`` path against the app's automation write rules.

    Mirrors the app's containment (relative forward-slash paths under the
    write root only — absolute paths, ``..`` and escaping paths are
    refused; see ``docs/control-protocol.md``) with a local pre-check so
    the agent gets a clear error before the round trip.

    :param path: Candidate save path.
    :returns: The unchanged relative path.
    :raises LiveError: Empty, absolute, backslashed, or traversal path.
    """
    cleaned = str(path).strip()
    if not cleaned:
        raise LiveError("doc_save path must not be empty")
    if "\\" in cleaned:
        raise LiveError("doc_save path must use forward slashes")
    if cleaned.startswith(("/", "~")) or _DRIVE_RE.match(cleaned):
        raise LiveError(
            "doc_save path must be relative (inside the app's automation write root)"
        )
    if any(part in ("", ".", "..") for part in cleaned.split("/")):
        raise LiveError(
            "doc_save path must stay inside the app's automation write root"
        )
    return cleaned


def _channel_error(app: str, method: str, exc: LiveError) -> LiveError:
    """Turn a channel/protocol failure into an honest, truncated LiveError.

    :param app: App id.
    :param method: Control method attempted.
    :param exc: Underlying failure.
    :returns: LiveError naming the app as not running, or the failing
        method with the app's error text (truncated to 200 chars — log-safe,
        never pixels/params).
    """
    message = str(exc)
    if message.startswith("cannot reach") or "is not running" in message:
        return LiveError(
            f"{app} is not running — start it from the App panel or Refresh"
        )
    return LiveError(f"{method} failed: {message[:200]}")


def _optional_int(value: Any) -> int | None:
    """Best-effort int coercion (None when absent/unparseable)."""
    if isinstance(value, bool):
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _read_png_file(path: str, *, max_bytes: int = 64 * 1024 * 1024) -> bytes | None:
    """Read back a screenshot the app saved to ``path`` (never logged).

    :param path: Capture file written by ``ui.screenshot {path}``.
    :param max_bytes: Sanity cap (refuse absurd files).
    :returns: Raw PNG bytes, or None when missing/empty/huge/not a PNG.
    """
    try:
        with open(path, "rb") as handle:
            raw = handle.read(max_bytes + 1)
    except OSError:
        return None
    if not raw or len(raw) > max_bytes or raw[:8] != _PNG_MAGIC:
        return None
    return raw


def _extract_png_bytes(reply: dict[str, Any]) -> bytes | None:
    """Find base64 PNG bytes in a ``ui.screenshot`` reply (never logged).

    :param reply: Decoded ``result`` of ``ui.screenshot``.
    :returns: Raw PNG bytes, or None when no payload decodes to a PNG.
    """
    candidates: list[str] = []
    for key in _SCREENSHOT_KEYS:
        value = reply.get(key)
        if isinstance(value, str) and value:
            candidates.append(value)
    for key, value in reply.items():
        if key not in _SCREENSHOT_KEYS and isinstance(value, str) and value:
            candidates.append(value)
    for text in candidates:
        try:
            raw = base64.b64decode(text, validate=True)
        except (ValueError, base64.binascii.Error):
            continue
        if raw[:8] == _PNG_MAGIC:
            return raw
    return None


__all__ = [
    "LAUNCHABLE_APPS",
    "LAUNCH_PORTS",
    "LAUNCH_TIMEOUT_S",
    "LIVE_APPS",
    "START_HINTS",
    "LiveDocument",
    "LiveError",
    "LiveExecutor",
    "LiveManager",
    "LiveStatus",
    "desktop_launch_argv",
    "launch_app",
    "live_configs_from_env",
    "live_manager_from_env",
    "resolve_desktop_binary",
    "sanitize_filename",
]
