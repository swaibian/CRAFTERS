"""Crafter controller FastAPI service (port 8790).

Wiring chain (STEP B5)::

    uvicorn controller.service:app --port 8790
      → create_app() builds the FastAPI app
      → POST /api/settings/profiles (CRUD, controller/settings.py)
      → GET  /api/teams (Scaico_Teams JSON passthrough)
      → POST /api/files/open (multipart upload → session work dir → inspect)
      → POST /api/chat/stream (SSE, same event names as swaibian-one
         send_task_stream: response.started/text.delta/tool.call/tool.result/
         response.completed/response.error)
      → GET  /api/chat/history (per-session transcript)

Session roots confinement reuses ``gateway.backends.SessionRegistry`` via
:meth:`ServiceState.check_session_path` (same lexical + symlink check).

SW-REQ: SW-REQ-STREAM (controller HTTP surface, TC-B).
"""

from __future__ import annotations

import json
import secrets
import time
from pathlib import Path
from typing import Annotated, Any

import anyio
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from gateway.backends import RootsViolation, SessionRegistry

from .agent import brain_from_profile, run_agent_loop
from .documents import (
    DocumentError,
    DocumentRegistry,
    PdfAdapter,
    PhotoAdapter,
    SheetAdapter,
)
from .live import (
    LAUNCHABLE_APPS,
    LIVE_APPS,
    START_HINTS,
    LiveError,
    LiveExecutor,
    LiveManager,
    launch_app,
    live_manager_from_env,
    sanitize_filename,
)
from .llm import MockBrain
from .logger import get_logger, safe_event
from .settings import SettingsError, SettingsStore, list_teams

log = get_logger()

CHAT_HISTORY_LIMIT = 200
UPLOAD_SUFFIXES = (
    ".xlsx",
    ".xlsm",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".tiff",
    ".pdf",
)


def sse_frame(event: str, payload: dict[str, Any]) -> str:
    """Frame one SSE event (``event:``/``data:`` lines + blank line).

    :param event: Event name (e.g. ``response.started``).
    :param payload: JSON-serializable data.
    :returns: Framed SSE text.
    """
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


class ServiceState:
    """Per-process service state: settings, sessions, docs, history.

    :param settings: Settings store (profiles + gateway + Scaico + team).
    :param work_root: Root dir holding per-session work dirs.
    :param live: Live-app manager (defaults to env-based; tests inject
        stub configs here).
    """

    def __init__(
        self,
        settings: SettingsStore | None = None,
        work_root: str | Path | None = None,
        live: LiveManager | None = None,
    ) -> None:
        self.settings = settings or SettingsStore()
        root = (
            Path(work_root) if work_root else Path(__file__).resolve().parent / "work"
        )
        self.work_root = root
        self.work_root.mkdir(parents=True, exist_ok=True)
        self.sessions = SessionRegistry(default_roots=[self.work_root])
        self.live = live if live is not None else live_manager_from_env()
        self._registries: dict[str, DocumentRegistry] = {}
        self._history: dict[str, list[dict[str, Any]]] = {}
        self._mock = MockBrain()

    def session_work_dir(self, session_id: str) -> Path:
        """Return (creating) the session work dir + registry entry.

        :param session_id: Session id.
        :returns: Work dir path confined to the work root.
        """
        if self.sessions.get(session_id) is None:
            self.sessions.create(session_id, "local", roots=[self.work_root])
        work = self.work_root / session_id
        work.mkdir(parents=True, exist_ok=True)
        if session_id not in self._registries:
            self._registries[session_id] = DocumentRegistry(work)
        return work

    def registry_for(self, session_id: str) -> DocumentRegistry:
        """Return the session document registry (creating the session).

        :param session_id: Session id.
        """
        self.session_work_dir(session_id)
        return self._registries[session_id]

    def check_session_path(self, session_id: str, path: str | Path) -> Path:
        """Confine a path to session roots (gateway SessionRegistry check).

        :param session_id: Session id.
        :param path: Candidate path.
        :returns: Resolved path inside the session roots.
        :raises HTTPException: 404 unknown session, 403 escape attempt.
        """
        try:
            return self.sessions.check_path(session_id, path)
        except RootsViolation as exc:
            message = str(exc)
            if message == "unknown session":
                raise HTTPException(status_code=404, detail="unknown session") from None
            raise HTTPException(status_code=403, detail="access denied") from None

    def append_history(
        self,
        session_id: str,
        role: str,
        text: str,
        *,
        team: str | None = None,
        model: str | None = None,
    ) -> None:
        """Append a transcript entry (bounded per session).

        :param session_id: Session id.
        :param role: ``user`` or ``assistant``.
        :param text: Message text.
        :param team: Owning team id (recorded on the entry when known).
        :param model: Resolved model name (recorded on the entry when known).
        """
        entries = self._history.setdefault(session_id, [])
        entry: dict[str, Any] = {
            "role": role,
            "text": text,
            "at": time.time(),
            "team": team,
            "model": model,
        }
        entries.append(entry)
        del entries[: max(0, len(entries) - CHAT_HISTORY_LIMIT)]

    def history(self, session_id: str) -> list[dict[str, Any]]:
        """Return the session transcript (oldest first)."""
        return list(self._history.get(session_id, []))


def adapter_for_suffix(suffix: str) -> str:
    """Map an upload suffix to an adapter kind.

    :param suffix: Lower-cased file suffix.
    :returns: ``sheet`` | ``photo`` | ``pdf``.
    :raises HTTPException: 415 unsupported type.
    """
    if suffix in SheetAdapter.SUFFIXES:
        return "sheet"
    if suffix in PhotoAdapter.SUFFIXES:
        return "photo"
    if suffix in PdfAdapter.SUFFIXES:
        return "pdf"
    raise HTTPException(status_code=415, detail=f"unsupported file type: {suffix}")


MODELS_CACHE_TTL_S = 60.0
MODELS_FETCH_TIMEOUT_S = 15.0
MODELS_RESOLVE_TIMEOUT_S = 5.0
CONVERSATION_TITLE_LIMIT = 60

# In-memory model list cache: profile_id → (fetched_at_epoch, [model ids]).
_models_cache: dict[str, tuple[float, list[str]]] = {}

# First-doc-kind → sidebar app label (unknown kinds map to None).
DOC_KIND_APP_LABELS = {"sheet": "gridcraft", "photo": "photocraft", "pdf": "pdfcraft"}


class ModelsFetchError(Exception):
    """Live model-list fetch failed (safe message; keys never attached)."""


def fetch_profile_models(
    profile: Any, *, timeout: float = MODELS_FETCH_TIMEOUT_S
) -> tuple[list[str], bool]:
    """Live-fetch a profile's model ids (``GET {api_base}/models``, cached 60s).

    The profile key travels in the ``Authorization: Bearer`` header only and
    is never logged or returned. Responses are parsed OpenAI-style
    (``{data: [{id}]}``); any other JSON shape yields an empty list.

    :param profile: Server-side profile (includes the key).
    :param timeout: HTTP timeout seconds.
    :returns: ``(model_ids, cached)`` — ``cached`` is True on a cache hit.
    :raises ModelsFetchError: Unreachable endpoint or non-2xx status.
    """
    import httpx

    now = time.monotonic()
    hit = _models_cache.get(profile.id)
    if hit is not None and now - hit[0] < MODELS_CACHE_TTL_S:
        return (list(hit[1]), True)
    try:
        response = httpx.get(
            f"{profile.api_base.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {profile.api_key}"},
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        raise ModelsFetchError("models endpoint unreachable") from exc
    if response.status_code >= 400:
        raise ModelsFetchError(
            f"models endpoint answered status {response.status_code}"
        )
    try:
        payload = response.json()
        raw = payload.get("data", [])
        models = [str(m.get("id", "")) for m in raw if isinstance(m, dict)]
        models = [m for m in models if m]
    except ValueError as exc:
        raise ModelsFetchError("models endpoint returned unreadable data") from exc
    _models_cache[profile.id] = (now, list(models))
    log.info(
        "models fetched: %s",
        safe_event(
            event="models_fetch", profile_id=profile.id, count=len(models), ok=True
        ),
    )
    return (models, False)


def resolve_chat_model(
    profile: Any | None,
    requested_model: str | None,
) -> tuple[str | None, str | None]:
    """Resolve the model for one chat run (no network on this path).

    Rules:

    - explicit ``model`` override wins as-is (the endpoint validates it
      against the live list and answers 400 when unknown — see below);
    - else the profile's ``default_model`` when non-blank;
    - else ``None`` (the caller falls back to the provider's first live
      model, or fails closed with a 400 naming the missing default).

    ``profile_id`` in the request body is honored: when it names a stored
    profile, that profile — not the server-side active pointer — drives
    the run. The view sends it on every message (see ``App.tsx``), so a
    stale active pointer can never silently bill the wrong endpoint.

    :param profile: Server-side profile (or None for MockBrain).
    :param requested_model: Explicit ``model`` override (or None).
    :returns: ``(resolved_model_or_None, error_or_None)`` — ``error`` is
        set only when no usable model exists (empty default + no request).
    """
    if requested_model:
        return (requested_model, None)
    if profile is None:
        return (None, None)
    default = str(getattr(profile, "default_model", "") or "").strip()
    if default:
        return (default, None)
    return (
        None,
        (
            "no default model configured for this profile — "
            "set one in Settings (Default model) or pick a model in chat"
        ),
    )


def resolve_profile(
    settings: Any,
    requested_profile_id: str | None,
) -> tuple[Any | None, str | None]:
    """Resolve which profile drives one chat run.

    :param settings: :class:`SettingsStore`.
    :param requested_profile_id: ``profile_id`` from the request body.
    :returns: ``(profile_or_None, error_or_None)`` — a named-but-unknown
        id is a 400 (fail closed: never silently use another endpoint).
    """
    if requested_profile_id:
        profile = settings.get_profile(str(requested_profile_id))
        if profile is None:
            return (None, "unknown profile")
        return (profile, None)
    return (settings.active_profile(), None)


def resolve_team(team_id: str | None) -> dict[str, Any] | None:
    """Resolve a chat ``team_id`` against ``list_teams()`` (behaviorally real).
    :returns: The team summary, or None when no team was requested.
    :raises HTTPException: 400 unknown team.
    """
    if not team_id:
        return None
    for team in list_teams():
        if team.get("id") == team_id:
            return team
    raise HTTPException(status_code=400, detail="unknown team")


def create_app(state: ServiceState | None = None) -> FastAPI:
    """Build the controller FastAPI app.

    :param state: Service state override (tests inject tmp dirs here).
    :returns: Configured :class:`FastAPI` app (``app.state.controller``).
    """
    app = FastAPI(title="crafter-controller", version="0.1.0")
    owned = state or ServiceState()
    app.state.controller = owned

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "service": "crafter-controller"}

    # -- settings: profiles CRUD -------------------------------------------

    @app.get("/api/settings/profiles")
    async def profiles_list() -> dict[str, Any]:
        active = owned.settings.active_profile()
        return {
            "profiles": owned.settings.list_profiles(),
            "active_profile_id": active.id if active else None,
        }

    @app.post("/api/settings/profiles", status_code=201)
    async def profiles_create(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return {"profile": owned.settings.create_profile(payload)}
        except SettingsError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @app.put("/api/settings/profiles/{profile_id}")
    async def profiles_update(
        profile_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            return {"profile": owned.settings.update_profile(profile_id, payload)}
        except SettingsError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @app.delete("/api/settings/profiles/{profile_id}")
    async def profiles_delete(profile_id: str) -> dict[str, Any]:
        removed = owned.settings.delete_profile(profile_id)
        if not removed:
            raise HTTPException(status_code=404, detail="unknown profile")
        return {"deleted": profile_id}

    @app.post("/api/settings/profiles/test")
    async def profiles_test(payload: dict[str, Any]) -> dict[str, Any]:
        """Test an endpoint+key without storing anything.

        Body: ``{api_base, api_key?, profile_id?, default_model?}`` — when
        ``profile_id`` names a stored profile, its key is used unless
        ``api_key`` overrides it. Hits ``GET {base}/models`` (OpenAI
        convention); any 2xx/401 counts as "reachable" (401 proves the
        endpoint speaks OpenAI + the key is wrong, which is still a
        successful connection test). The key is never echoed back.

        :param payload: Test request body.
        :returns: ``{ok, status?, models?, error?}`` — no secrets ever.
        """
        from .llm import LlmClient, LlmError

        api_base = str(payload.get("api_base", "") or "").strip()
        api_key = str(payload.get("api_key", "") or "")
        model = str(payload.get("default_model", "") or "").strip() or "test"
        profile_id = payload.get("profile_id")
        if profile_id:
            stored = owned.settings.get_profile(str(profile_id))
            if stored is None:
                raise HTTPException(status_code=404, detail="unknown profile")
            if not api_base:
                api_base = stored.api_base
            if not api_key:
                api_key = stored.api_key
            if not payload.get("default_model"):
                model = stored.default_model or model
        if not api_base:
            raise HTTPException(status_code=400, detail="api_base is required")
        try:
            result = LlmClient(
                api_base=api_base,
                api_key=api_key,
                default_model=model,
                timeout_s=15.0,
            ).ping()
        except LlmError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, **result}

    @app.get("/api/settings/profiles/models")
    async def profiles_models(profile_id: str) -> dict[str, Any]:
        """List a profile's live models (``GET {api_base}/models``, cached 60s).

        :param profile_id: Stored profile id (query param).
        :returns: ``{models: [{id}], cached}`` — keys never echoed/logged.
        :raises HTTPException: 404 unknown profile, 502 unreachable endpoint.
        """
        profile = owned.settings.get_profile(profile_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="unknown profile")
        try:
            models, cached = fetch_profile_models(profile)
        except ModelsFetchError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from None
        return {"models": [{"id": m} for m in models], "cached": cached}

    @app.get("/api/settings/active")
    async def settings_active() -> dict[str, Any]:
        active = owned.settings.active_profile()
        return {
            "active_profile_id": active.id if active else None,
            "mock": active is None,
            "gateway_endpoint": owned.settings.get_gateway_endpoint(),
            "scaico": owned.settings.scaico_status(),
            "selected_team_id": owned.settings.get_selected_team(),
        }

    @app.put("/api/settings/active")
    async def settings_set_active(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            owned.settings.set_active_profile(payload.get("profile_id"))
        except SettingsError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        return await settings_active()

    @app.put("/api/settings/gateway")
    async def settings_gateway(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            endpoint = owned.settings.set_gateway_endpoint(
                str(payload.get("endpoint", ""))
            )
        except SettingsError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        return {"gateway_endpoint": endpoint}

    @app.put("/api/settings/scaico-key")
    async def settings_scaico_key(payload: dict[str, Any]) -> dict[str, Any]:
        return owned.settings.set_scaico_key(str(payload.get("api_key", "")))

    @app.post("/api/settings/scaico-key/test")
    async def settings_scaico_key_test(payload: dict[str, Any]) -> dict[str, Any]:
        """Validate the stored Scaico key or an ``{"api_key"}`` body override.

        Hits ``GET {base}/api/info`` with the key in the ``X-API-Key`` header
        only (mirrors swaibian-one ``validate_api_key``). The key is never
        echoed back or logged.

        :param payload: Optional ``{"api_key"}`` override (stored key otherwise).
        :returns: ``{ok, latency_ms?, error?}`` — no secrets ever.
        """
        from .diagnostics import scaico_info

        override = str(payload.get("api_key", "") or "")
        key = override or owned.settings.get_scaico_key()
        if not key:
            return {"ok": False, "error": "no scaico key configured"}
        result = scaico_info(key)
        log.info(
            "scaico key tested: %s",
            safe_event(event="scaico_test", ok=bool(result["ok"])),
        )
        return result

    @app.get("/api/diagnostics")
    async def diagnostics() -> dict[str, Any]:
        """Run connection probes (gateway/controller/scaico/litellm) + recent log.

        Probes run sequentially on each call (each bounded ≤5s). Keys are
        never logged or returned.

        :returns: ``{checks: {gateway, controller, scaico, litellm}, recent}``
            where ``recent`` is newest-first (max 20).
        """
        from .diagnostics import probe_all, recent

        return {"checks": probe_all(owned.settings), "recent": recent(20)}

    @app.put("/api/settings/team")
    async def settings_team(payload: dict[str, Any]) -> dict[str, Any]:
        owned.settings.set_selected_team(payload.get("team_id"))
        return {"selected_team_id": owned.settings.get_selected_team()}

    # -- teams passthrough ---------------------------------------------------

    @app.get("/api/teams")
    async def teams_list() -> dict[str, Any]:
        return {"teams": list_teams()}

    # -- files: upload → session work dir → adapter inspect ------------------

    @app.post("/api/files/open", status_code=201)
    async def files_open(
        file: Annotated[UploadFile, File(...)],
        session_id: Annotated[str, Form()] = "default",
    ) -> dict[str, Any]:
        filename = file.filename or "upload.bin"
        suffix = Path(filename).suffix.lower()
        kind = adapter_for_suffix(suffix)
        work = owned.session_work_dir(session_id)
        staged = work / f"upload_{secrets.token_hex(4)}_{Path(filename).name}"
        # Confine the staged path (defense in depth — work dir is in roots).
        owned.check_session_path(session_id, staged)
        async with await anyio.open_file(staged, "wb") as handle:
            while chunk := await file.read(65536):
                await handle.write(chunk)
        await file.close()
        registry = owned.registry_for(session_id)
        try:
            if kind == "sheet":
                doc = SheetAdapter(registry).open(staged, filename)
                evidence: dict[str, Any] = SheetAdapter(registry).inspect(doc.doc_id)
            elif kind == "photo":
                doc = PhotoAdapter(registry).open(staged, filename)
                evidence = PhotoAdapter(registry).inspect(doc.doc_id)
            else:
                doc = PdfAdapter(registry).open(staged, filename)
                evidence = PdfAdapter(registry).inspect(doc.doc_id)
        except DocumentError as exc:
            staged.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=str(exc)) from None
        log.info(
            "file opened: %s",
            safe_event(event="file_open", adapter=kind, session_id=session_id, ok=True),
        )
        return {
            "doc_id": doc.doc_id,
            "kind": doc.kind,
            # Compat aliases for the view contract (app/name/session/thumbnail):
            # the view maps kind→app and source_name→name defensively, but
            # serving both shapes keeps old + new views working.
            "app": doc.kind,
            "name": doc.source_name,
            "source_name": doc.source_name,
            "source": doc.source,
            "live_app": doc.live_app,
            "session_id": session_id,
            "thumbnail_url": f"/api/files/{doc.doc_id}/thumbnail?session_id={session_id}",
            "work_path": str(doc.work_path),
            "inspect": evidence,
        }

    @app.get("/api/files/{doc_id}")
    async def files_inspect(doc_id: str, session_id: str = "default") -> dict[str, Any]:
        registry = owned.registry_for(session_id)
        doc = registry.get(doc_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="unknown document")
        try:
            if doc.kind == "sheet":
                evidence = SheetAdapter(registry).inspect(doc_id)
            elif doc.kind == "photo":
                evidence = PhotoAdapter(registry).inspect(doc_id)
            else:
                evidence = PdfAdapter(registry).inspect(doc_id)
        except DocumentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        return {
            "doc_id": doc_id,
            "kind": doc.kind,
            # Compat aliases for the view contract (see files_open).
            "app": doc.kind,
            "name": doc.source_name,
            "source_name": doc.source_name,
            "source": doc.source,
            "live_app": doc.live_app,
            "session_id": session_id,
            "thumbnail_url": f"/api/files/{doc_id}/thumbnail?session_id={session_id}",
            "inspect": evidence,
        }

    @app.get("/api/files/{doc_id}/download")
    async def files_download(doc_id: str, session_id: str = "default") -> FileResponse:
        registry = owned.registry_for(session_id)
        doc = registry.get(doc_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="unknown document")
        owned.check_session_path(session_id, doc.work_path)
        return FileResponse(
            path=str(doc.work_path),
            filename=f"result_{doc.source_name}",
        )

    @app.get("/api/files/{doc_id}/thumbnail")
    async def files_thumbnail(doc_id: str, session_id: str = "default") -> FileResponse:
        """Serve a preview image for an open document (the "see" pixels).

        Photos serve the working copy itself; PDFs render a page-0 thumbnail
        via :meth:`PdfAdapter.render_thumbnail`; sheets have no pixels →
        404 (the view hides the preview and keeps the inspect summary).

        Session isolation: the doc must live in ``session_id``'s registry
        (else 404) and every served path passes
        :meth:`ServiceState.check_session_path` (403 on escape).

        :param doc_id: Open document id.
        :param session_id: Owning session (query param).
        """
        registry = owned.registry_for(session_id)
        doc = registry.get(doc_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="unknown document")
        owned.check_session_path(session_id, doc.work_path)
        if doc.kind == "photo":
            return FileResponse(path=str(doc.work_path))
        if doc.kind == "pdf":
            try:
                thumb = PdfAdapter(registry).render_thumbnail(doc_id)
            except DocumentError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from None
            owned.check_session_path(session_id, thumb)
            return FileResponse(path=str(thumb), media_type="image/png")
        raise HTTPException(status_code=404, detail="no thumbnail for this document")

    # -- live: desktop apps started with --control as chat objects -----------

    @app.get("/api/live/status")
    async def live_status() -> dict[str, Any]:
        """Probe every live-app control channel (never fails, never raises).

        :returns: ``{apps: [{app, running, mode, launchable, last_error?, hint?}]}``
            where ``mode`` is ``"bridge"`` (live) or ``"down"``,
            ``launchable`` marks the TCP apps the Launch button may start,
            and ``hint`` is the exact ``--control`` start command when down.
        """
        entries: list[dict[str, Any]] = []
        for app_name in LIVE_APPS:
            state = await owned.live.status(app_name)
            entry: dict[str, Any] = {
                "app": state.app,
                "running": state.running,
                "mode": state.mode,
                "launchable": app_name in LAUNCHABLE_APPS,
            }
            if state.last_error:
                entry["last_error"] = state.last_error
            if state.hint:
                entry["hint"] = state.hint
            entries.append(entry)
        return {"apps": entries}

    @app.get("/api/live/documents")
    async def live_documents(app: str = "photocraft") -> dict[str, Any]:
        """List the documents open in a live desktop window.

        :param app: App id (query param, default ``photocraft``).
        :returns: ``{app, running, active, documents: [{index, name,
            width?, height?, dirty, active}]}``.
        :raises HTTPException: 400 unknown app, 502 app down / no documents.
        """
        if app not in LIVE_APPS:
            raise HTTPException(status_code=400, detail=f"unknown app: {app}")
        try:
            documents, active = await owned.live.list_documents(app)
        except LiveError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from None
        return {
            "app": app,
            "running": True,
            "active": active,
            "documents": [
                {
                    "index": doc.index,
                    "name": doc.name,
                    "width": doc.width,
                    "height": doc.height,
                    "dirty": doc.dirty,
                    "active": doc.active,
                }
                for doc in documents
            ],
        }

    @app.post("/api/live/launch")
    async def live_launch(payload: dict[str, Any]) -> dict[str, Any]:
        """Start a down desktop app and wait for its control channel.

        Spawns only the allowlisted GUI binaries (photocraft/gridcraft)
        with fixed argv — no request data ever reaches the command line.
        The token travels via a 0600 file and never into logs/responses.
        Idempotent: an already-running app returns immediately.

        Body: ``{app}``.
        :param payload: ``{app}``.
        :returns: ``{app, running, mode, pid}``.
        :raises HTTPException: 400 unknown app, 409 app has no TCP
            control channel (pdfcraft stays manual — hint included),
            502 binary missing / spawn failed / channel silent past the
            timeout (the app keeps starting; Refresh picks it up).
        """
        app = str(payload.get("app", "photocraft"))
        if app not in LIVE_APPS:
            raise HTTPException(status_code=400, detail=f"unknown app: {app}")
        if app not in LAUNCHABLE_APPS:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": f"{app} has no TCP control channel — start it by hand",
                    "hint": START_HINTS.get(app, ""),
                },
            )
        try:
            return await launch_app(owned.live, app)
        except LiveError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from None

    @app.post("/api/live/attach", status_code=201)
    async def live_attach(payload: dict[str, Any]) -> dict[str, Any]:
        """Capture a live-window document as the chat object (import model).

        Snapshots the window via ``ui.screenshot`` into the session work
        dir and registers it as a normal photo document with
        ``source="live"`` provenance. Chat, thumbnail, download, and the
        agent edit loop then work unchanged — on the attached copy, never
        on the user's live window.

        Body: ``{session_id?, app, document?}`` — ``document`` is the
        engine document index (defaults to the window's active document).

        :param payload: ``{session_id?, app, document?}``.
        :returns: Same shape as ``POST /api/files/open`` plus
            ``source: "live"`` and ``live_app``.
        :raises HTTPException: 400 unknown app/document, 502 app down or
            uncapturable window (occluded windows stop rendering — focus
            the app and retry).
        """
        session_id = str(payload.get("session_id", "default"))
        app = str(payload.get("app", "photocraft"))
        if app not in LIVE_APPS:
            raise HTTPException(status_code=400, detail=f"unknown app: {app}")
        raw_index = payload.get("document")
        index: int | None = None
        if raw_index is not None:
            try:
                index = int(raw_index)
            except (TypeError, ValueError):
                raise HTTPException(
                    status_code=400, detail="document must be an index"
                ) from None
        work = owned.session_work_dir(session_id)
        try:
            documents, active = await owned.live.list_documents(app)
        except LiveError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from None
        target = index if index is not None else active
        if target is None:
            target = documents[0].index
        live_doc = next((d for d in documents if d.index == target), None)
        if live_doc is None:
            raise HTTPException(
                status_code=400, detail=f"unknown live document: {target}"
            )
        try:
            png = await owned.live.screenshot_png(app, document=live_doc.index)
        except LiveError as exc:
            message = str(exc)
            if message.startswith("unknown live document"):
                raise HTTPException(status_code=400, detail=message) from None
            raise HTTPException(status_code=502, detail=message) from None
        display = f"{live_doc.name} (live {app})"
        staged = (
            work
            / f"live_{app}_{sanitize_filename(live_doc.name)}_{secrets.token_hex(4)}.png"
        )
        # Confine the staged path (defense in depth — work dir is in roots).
        owned.check_session_path(session_id, staged)
        staged.write_bytes(png)
        registry = owned.registry_for(session_id)
        try:
            doc = PhotoAdapter(registry).open(staged, display)
            evidence: dict[str, Any] = PhotoAdapter(registry).inspect(doc.doc_id)
        except DocumentError as exc:
            staged.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=str(exc)) from None
        doc.source = "live"
        doc.live_app = app
        doc.live_index = live_doc.index
        log.info(
            "live file attached: %s",
            safe_event(event="live_attach", app=app, session_id=session_id, ok=True),
        )
        return {
            "doc_id": doc.doc_id,
            "kind": doc.kind,
            "app": doc.kind,
            "name": doc.source_name,
            "source_name": doc.source_name,
            "source": doc.source,
            "live_app": doc.live_app,
            "live_index": doc.live_index,
            "session_id": session_id,
            "thumbnail_url": f"/api/files/{doc.doc_id}/thumbnail?session_id={session_id}",
            "work_path": str(doc.work_path),
            "inspect": evidence,
        }

    # -- verify: snapshot / restore / record-view (sidebar detail actions) ------

    @app.post("/api/verify/snapshot")
    async def verify_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
        """Snapshot the open document's working copy (pre-edit checkpoint).

        Body: ``{session_id, doc_id?}`` — ``doc_id`` defaults to the
        session's first open document. Session isolation: the doc must live
        in the session registry (else 404); the snapshot path never leaves
        the server (only the revision number is returned — no paths, no
        tokens, no keys).

        :param payload: ``{session_id, doc_id?}``.
        :returns: ``{ok, summary}`` for the view verify row.
        """
        session_id = str(payload.get("session_id", "default"))
        registry = owned.registry_for(session_id)
        doc_id = payload.get("doc_id")
        doc = (
            registry.get(str(doc_id))
            if doc_id
            else next(iter(registry._docs.values()), None)
        )
        if doc is None:
            raise HTTPException(status_code=404, detail="unknown document")
        revision = registry.snapshot(doc.doc_id, label="verify:snapshot")
        log.info(
            "verify snapshot: %s",
            safe_event(
                event="verify_snapshot",
                session_id=session_id,
                revision=revision,
                ok=True,
            ),
        )
        return {"ok": True, "summary": f"Snapshot revision {revision}."}

    @app.post("/api/verify/restore")
    async def verify_restore(payload: dict[str, Any]) -> dict[str, Any]:
        """Roll the working copy back to a prior revision.

        Body: ``{session_id, doc_id?, revision?}`` — ``revision`` defaults
        to the latest snapshot before the current one. Same session
        isolation as snapshot; unknown doc/revision → 404/400.

        :param payload: ``{session_id, doc_id?, revision?}``.
        :returns: ``{ok, summary}`` for the view verify row.
        """
        session_id = str(payload.get("session_id", "default"))
        registry = owned.registry_for(session_id)
        doc_id = payload.get("doc_id")
        doc = (
            registry.get(str(doc_id))
            if doc_id
            else next(iter(registry._docs.values()), None)
        )
        if doc is None:
            raise HTTPException(status_code=404, detail="unknown document")
        if not doc.revisions:
            raise HTTPException(status_code=400, detail="no snapshots yet")
        target = payload.get("revision")
        revision = int(target) if target is not None else max(doc.revisions)
        try:
            registry.restore(doc.doc_id, revision)
        except DocumentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        owned.check_session_path(session_id, doc.work_path)
        log.info(
            "verify restore: %s",
            safe_event(
                event="verify_restore",
                session_id=session_id,
                revision=revision,
                ok=True,
            ),
        )
        return {"ok": True, "summary": f"Restored revision {revision}."}

    @app.post("/api/verify/record-view")
    async def verify_record_view(payload: dict[str, Any]) -> dict[str, Any]:
        """Summarize the session's evidence ledger (claim counts + revisions).

        Body: ``{session_id, doc_id?}``. The agent-run ledgers are per-run
        (they ride ``response.completed`` as ``records``); this endpoint
        reports what persists server-side: transcript counts + the open
        document's revision history. Read-only: never mutates, never leaks
        content (counts/hashes only).

        :param payload: ``{session_id, doc_id?}``.
        :returns: ``{ok, summary}`` for the view verify row.
        """
        session_id = str(payload.get("session_id", "default"))
        registry = owned.registry_for(session_id)
        entries = owned.history(session_id)
        users = sum(1 for e in entries if e.get("role") == "user")
        assistants = sum(1 for e in entries if e.get("role") == "assistant")
        doc_id = payload.get("doc_id")
        doc = registry.get(str(doc_id)) if doc_id else None
        if doc_id is not None and doc is None:
            raise HTTPException(status_code=404, detail="unknown document")
        rev = f"revision {doc.revision}" if doc is not None else "no document open"
        return {
            "ok": True,
            "summary": (f"{users} user / {assistants} assistant messages, {rev}."),
        }

    # -- conversations: sidebar backend (derived from history + registries) ---

    @app.get("/api/conversations")
    async def conversations_list() -> dict[str, Any]:
        """List sessions with history or docs, newest-first (sidebar backend).

        :returns: ``{conversations: [{id (=session_id), app?, title,
            updated_at (epoch), message_count, doc_ids: []}]}`` where ``app``
            is the first doc kind mapped to its app label (or null), ``title``
            is the first user message truncated to 60 chars, and
            ``updated_at`` is the latest history timestamp (0 when the
            session has docs but no history yet).
        """
        items: list[dict[str, Any]] = []
        session_ids = set(owned._history) | set(owned._registries)
        for session_id in session_ids:
            entries = owned._history.get(session_id, [])
            registry = owned._registries.get(session_id)
            doc_ids = list(registry._docs.keys()) if registry is not None else []
            if not entries and not doc_ids:
                continue
            first_user = next((e for e in entries if e.get("role") == "user"), None)
            title = str(first_user.get("text", "")) if first_user else ""
            if len(title) > CONVERSATION_TITLE_LIMIT:
                title = title[:CONVERSATION_TITLE_LIMIT]
            first_kind = ""
            if registry is not None:
                for doc_id in doc_ids:
                    doc = registry.get(doc_id)
                    if doc is not None:
                        first_kind = doc.kind
                        break
            items.append(
                {
                    "id": session_id,
                    "app": DOC_KIND_APP_LABELS.get(first_kind),
                    "title": title,
                    "updated_at": max((e.get("at", 0) for e in entries), default=0),
                    "message_count": len(entries),
                    "doc_ids": doc_ids,
                }
            )
        items.sort(key=lambda item: item["updated_at"], reverse=True)
        return {"conversations": items}

    @app.delete("/api/conversations/{conversation_id}")
    async def conversations_delete(conversation_id: str) -> dict[str, Any]:
        """Delete a conversation's history (files on disk are kept).

        Semantic: clears the session's transcript entries only; open document
        working copies and staged files stay on disk (re-upload is never
        required to keep working — the docs simply detach from the sidebar).

        :param conversation_id: Session id (= conversation id).
        :returns: ``{deleted: id}``.
        :raises HTTPException: 404 unknown conversation.
        """
        entries = owned._history.get(conversation_id, [])
        registry = owned._registries.get(conversation_id)
        doc_ids = list(registry._docs.keys()) if registry is not None else []
        if not entries and not doc_ids:
            raise HTTPException(status_code=404, detail="unknown conversation")
        owned._history.pop(conversation_id, None)
        log.info(
            "conversation deleted: %s",
            safe_event(
                event="conversation_delete", session_id=conversation_id, ok=True
            ),
        )
        return {"deleted": conversation_id}

    # -- chat: history + SSE stream ------------------------------------------

    @app.get("/api/chat/history")
    async def chat_history(session_id: str = "default") -> dict[str, Any]:
        return {"session_id": session_id, "messages": owned.history(session_id)}

    @app.post("/api/chat/stream")
    async def chat_stream(payload: dict[str, Any]) -> StreamingResponse:
        message = str(payload.get("message", ""))
        session_id = str(payload.get("session_id", "default"))
        doc_id = payload.get("doc_id")
        requested_model = payload.get("model")
        requested_team = payload.get("team_id")
        requested_profile_id = payload.get("profile_id")
        if not message.strip():
            raise HTTPException(status_code=400, detail="message is required")
        registry = owned.registry_for(session_id)
        open_doc = registry.get(str(doc_id)) if doc_id is not None else None
        if doc_id is not None and open_doc is None:
            raise HTTPException(status_code=404, detail="unknown document")
        team = resolve_team(str(requested_team) if requested_team is not None else None)
        team_id = str(team["id"]) if team else None
        profile, profile_error = resolve_profile(
            owned.settings,
            str(requested_profile_id) if requested_profile_id else None,
        )
        if profile_error is not None:
            raise HTTPException(status_code=400, detail=profile_error)
        profile_id = profile.id if profile else ""
        resolved_model, model_error = resolve_chat_model(
            profile, str(requested_model) if requested_model else None
        )
        if profile is not None and model_error is not None:
            raise HTTPException(status_code=400, detail=model_error)
        if profile is not None and resolved_model:
            try:
                live_models, _cached = fetch_profile_models(
                    profile, timeout=MODELS_RESOLVE_TIMEOUT_S
                )
            except ModelsFetchError:
                live_models = []  # fetch failed → allow requested; chat errors honestly
            if not live_models:
                # No list to validate against (unreachable endpoint): default
                # the empty-default profile to the first live model when the
                # fetch recovers below, else chat errors honestly.
                pass
            elif resolved_model not in live_models:
                if requested_model:
                    raise HTTPException(status_code=400, detail="unknown model")
                # Stored default drifted (renamed/retired upstream): fall
                # back to the first live model instead of sending a dead id.
                resolved_model = live_models[0]
                log.info(
                    "chat model fallback: %s",
                    safe_event(
                        event="model_fallback",
                        profile_id=profile_id,
                        model=resolved_model,
                        ok=True,
                    ),
                )
        is_live = bool(open_doc and open_doc.source == "live" and open_doc.live_app)
        live_app = str(open_doc.live_app or "") if is_live and open_doc else ""
        plan_fn, model_name, is_mock = brain_from_profile(
            profile,
            owned._mock,
            model_override=resolved_model,
            team=team,
            live=is_live,
            live_app=live_app,
        )
        owned.append_history(
            session_id, "user", message, team=team_id, model=model_name
        )

        async def _stream() -> Any:
            run_id = ""
            assistant_text = ""
            executor: LiveExecutor | None = None
            live_error = ""
            if is_live:
                status = await owned.live.status(live_app)
                if status.running:
                    executor = LiveExecutor(
                        manager=owned.live,
                        app=live_app,
                        document=open_doc.live_index if open_doc else None,
                    )
                else:
                    live_error = (
                        f"{live_app} is not running — start it from the "
                        "App panel or Refresh"
                    )

            async def _events() -> Any:
                if live_error:
                    # Honest refusal for live docs with a dead bridge — never
                    # fall back to editing the imported copy.
                    log.warning(
                        "live chat refused: %s",
                        safe_event(
                            event="chat_live_down",
                            app=live_app,
                            session_id=session_id,
                            error=live_error,
                            ok=False,
                        ),
                    )
                    yield {"type": "run.error", "message": live_error}
                    return
                async for event in run_agent_loop(
                    message,
                    doc_id=str(doc_id) if doc_id else None,
                    registry=registry,
                    plan_fn=plan_fn,
                    model_name=model_name,
                    is_mock=is_mock,
                    session_id=session_id,
                    executor=executor,
                    live_app=live_app,
                ):
                    yield event

            try:
                async for event in _events():
                    etype = event.get("type", "")
                    if etype == "run.started":
                        run_id = str(event.get("run_id", ""))
                        yield sse_frame(
                            "response.started",
                            {
                                "run_id": run_id,
                                "model": event.get("model", ""),
                                "mock": event.get("mock", True),
                                "team": team_id,
                            },
                        )
                    elif etype == "plan" and event.get("text"):
                        assistant_text += str(event["text"]) + "\n"
                        yield sse_frame(
                            "text.delta", {"delta": str(event["text"]) + "\n"}
                        )
                    elif etype == "tool.call":
                        yield sse_frame(
                            "tool.call",
                            {
                                "name": event.get("name"),
                                "call_id": event.get("call_id"),
                                # Compat: the view contract reads `args`.
                                "args": event.get("arguments", {}),
                            },
                        )
                    elif etype == "tool.result":
                        ok_result = bool(event.get("ok"))
                        summary = (
                            f"{event.get('name')} ok"
                            if ok_result
                            else str(event.get("error", ""))
                        )
                        if ok_result and event.get("revision") is not None:
                            summary += f" (revision {event.get('revision')})"
                        yield sse_frame(
                            "tool.result",
                            {
                                "name": event.get("name"),
                                "ok": ok_result,
                                "error": event.get("error", ""),
                                # Compat: the view contract reads `summary`.
                                "summary": summary,
                            },
                        )
                    elif etype == "observe":
                        yield sse_frame(
                            "text.delta",
                            {
                                "delta": f"[observed revision {event.get('observation', {}).get('revision')}] \n"
                            },
                        )
                    elif etype == "run.completed":
                        assistant_text += str(event.get("summary", ""))
                        yield sse_frame(
                            "text.delta", {"delta": str(event.get("summary", ""))}
                        )
                        yield sse_frame(
                            "response.completed",
                            {
                                "run_id": run_id,
                                "records": event.get("records", []),
                                # Compat: the view contract reads `message_id`.
                                "message_id": run_id,
                            },
                        )
                    elif etype == "run.error":
                        yield sse_frame(
                            "response.error", {"message": str(event.get("message", ""))}
                        )
            except Exception:
                log.exception("chat stream failed")
                yield sse_frame("response.error", {"message": "stream failed"})
            owned.append_history(
                session_id, "assistant", assistant_text, team=team_id, model=model_name
            )

        log.info(
            "chat stream: %s",
            safe_event(
                event="chat_stream",
                session_id=session_id,
                profile_id=profile_id,
                model=model_name,
                team=team_id or "",
                ok=True,
            ),
        )
        return StreamingResponse(_stream(), media_type="text/event-stream")

    return app


app = create_app()


__all__ = [
    "CHAT_HISTORY_LIMIT",
    "CONVERSATION_TITLE_LIMIT",
    "DOC_KIND_APP_LABELS",
    "MODELS_CACHE_TTL_S",
    "MODELS_FETCH_TIMEOUT_S",
    "MODELS_RESOLVE_TIMEOUT_S",
    "ModelsFetchError",
    "ServiceState",
    "adapter_for_suffix",
    "app",
    "create_app",
    "fetch_profile_models",
    "resolve_chat_model",
    "resolve_profile",
    "resolve_team",
    "sse_frame",
]
