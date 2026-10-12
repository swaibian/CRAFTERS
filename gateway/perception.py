"""Perception synthesis: AccessKit proxy + canvasRect math + query_map backing.

Reference implementations for SW-REQ-A11Y (TC-C-01), grounded in
``06-PERCEPTION-AND-INTEGRATION.md``:

- **pdfcraft AccessKit-via-MCP** (spec §1.5/§1.6): pdfcraft already caches
  ``platform_output.accesskit_update`` per frame and emits
  ``{widgets: [{id, role, depth, enabled, clickable, focusable, label,
  value, description, rect, toggled, selected, focused}], count,
  truncated}`` — but only over the control channel. The gateway cannot fix
  the upstream MCP server from here; instead :class:`PerceptionTools`
  exposes ``craft_widgets`` which proxies the tree through the app backend
  (``ui.widgets`` / ``ui_widgets`` / control-call passthrough when the
  backend offers it, canned shape otherwise) with ``query`` / ``role`` /
  ``focused`` / ``limit`` filters, and :func:`redact_widgets` scrubs
  label/value/description (they may carry PII) for logs.
- **photocraft canvasRect synthesis** (spec §1.8): ``ui.pointer`` takes
  *document pixels* while ``ui.click``/``ui.move`` take *screen points*;
  ``views[]`` reports zoom/centre per window but no canvas rect. Given a
  view state ``{zoom, centre, canvas_size, view_size}``,
  :func:`doc_to_screen` / :func:`screen_to_doc` compute the mapping;
  :func:`synthesize_canvas_rect` derives the canvas rect for screenshot
  cropping (spec §2.1.1: crop the window screenshot to ``canvasRect``).
- **query_map backing** (TC-C-00 instantiation map): :class:`QueryMap`
  stores per-session resolved mappings (widget rects, canvas rects) so
  agents can reference ``query_map`` entries instead of re-resolving.

Upstream PR drafts live in ``docs/upstream-prs/`` (TC-C-01); the gateway
shim here is the fallback that works regardless of PR acceptance.

SW-REQ: SW-REQ-A11Y (perception references, TC-C-01).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from .auth import AuthStore
from .backends import BackendError, BackendManager, SessionRegistry
from .logger import get_logger, log_tool_ingress, safe_event

log = get_logger()

TOOL_NAMES = ("craft_widgets", "craft_map")

#: Widget fields that may carry user content — never logged verbatim.
WIDGET_TEXT_FIELDS = ("label", "value", "description")

#: Widget fields safe to log (structure only).
WIDGET_SAFE_FIELDS = (
    "id",
    "role",
    "depth",
    "enabled",
    "clickable",
    "focusable",
    "toggled",
    "selected",
    "focused",
)


def redact_widgets(widgets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return log-safe widget summaries (ids/roles/state only, no text).

    :param widgets: Raw widget mappings from the backend.
    :returns: Scrubbed copies holding :data:`WIDGET_SAFE_FIELDS` + a
        ``rect`` presence flag only.
    """
    scrubbed: list[dict[str, Any]] = []
    for widget in widgets:
        if not isinstance(widget, dict):
            continue
        entry = {key: widget.get(key) for key in WIDGET_SAFE_FIELDS if key in widget}
        entry["has_rect"] = widget.get("rect") is not None
        scrubbed.append(entry)
    return scrubbed


def filter_widgets(
    widgets: list[dict[str, Any]],
    *,
    query: str = "",
    role: str = "",
    focused: bool | None = None,
    limit: int = 500,
) -> tuple[list[dict[str, Any]], bool]:
    """Filter a widget tree (pdfcraft AccessKit semantics).

    :param widgets: Raw widget mappings.
    :param query: Case-insensitive substring over label/value/description.
    :param role: Exact role match (empty = all roles).
    :param focused: When not None, keep only matching focus state.
    :param limit: Max widgets returned (default 500, per upstream).
    :returns: ``(kept, truncated)``.
    """
    kept: list[dict[str, Any]] = []
    needle = query.lower()
    for widget in widgets:
        if not isinstance(widget, dict):
            continue
        if role and widget.get("role") != role:
            continue
        if focused is not None and bool(widget.get("focused")) != focused:
            continue
        if needle:
            haystack = " ".join(
                str(widget.get(field, "")) for field in WIDGET_TEXT_FIELDS
            ).lower()
            if needle not in haystack:
                continue
        kept.append(widget)
    truncated = len(kept) > limit
    return kept[:limit], truncated


def doc_to_screen(
    point: tuple[float, float],
    *,
    zoom: float,
    centre: tuple[float, float],
    view_size: tuple[float, float],
) -> tuple[float, float]:
    """Map document pixels → screen points (photocraft ``ui.pointer`` model).

    Screen = ``(doc - centre) * zoom + view_size / 2``.

    :param point: Document-space ``(x, y)`` in pixels.
    :param zoom: View zoom factor (> 0).
    :param centre: Document-space centre of the view.
    :param view_size: ``(width, height)`` of the view in screen points.
    :returns: Screen-space ``(x, y)``.
    :raises ValueError: Non-positive zoom.
    """
    if zoom <= 0:
        raise ValueError("zoom must be positive")
    return (
        (point[0] - centre[0]) * zoom + view_size[0] / 2,
        (point[1] - centre[1]) * zoom + view_size[1] / 2,
    )


def screen_to_doc(
    point: tuple[float, float],
    *,
    zoom: float,
    centre: tuple[float, float],
    view_size: tuple[float, float],
) -> tuple[float, float]:
    """Map screen points → document pixels (inverse of :func:`doc_to_screen`).

    :param point: Screen-space ``(x, y)``.
    :param zoom: View zoom factor (> 0).
    :param centre: Document-space centre of the view.
    :param view_size: ``(width, height)`` of the view in screen points.
    :returns: Document-space ``(x, y)`` in pixels.
    :raises ValueError: Non-positive zoom.
    """
    if zoom <= 0:
        raise ValueError("zoom must be positive")
    return (
        (point[0] - view_size[0] / 2) / zoom + centre[0],
        (point[1] - view_size[1] / 2) / zoom + centre[1],
    )


def synthesize_canvas_rect(
    *,
    zoom: float,
    centre: tuple[float, float],
    canvas_size: tuple[float, float],
    view_size: tuple[float, float],
) -> dict[str, float]:
    """Derive the canvas rect (document bounds in screen points).

    Maps the document origin ``(0, 0)`` and extent ``canvas_size`` through
    :func:`doc_to_screen`, yielding ``{x, y, w, h}`` for cropping a window
    screenshot to the canvas (spec §2.1.1).

    :param zoom: View zoom factor (> 0).
    :param centre: Document-space centre of the view.
    :param canvas_size: ``(width, height)`` of the document in pixels.
    :param view_size: ``(width, height)`` of the view in screen points.
    :returns: ``{x, y, w, h}`` screen-space rect of the canvas.
    :raises ValueError: Non-positive zoom or canvas size.
    """
    if zoom <= 0:
        raise ValueError("zoom must be positive")
    if canvas_size[0] <= 0 or canvas_size[1] <= 0:
        raise ValueError("canvas_size must be positive")
    x, y = doc_to_screen((0, 0), zoom=zoom, centre=centre, view_size=view_size)
    return {"x": x, "y": y, "w": canvas_size[0] * zoom, "h": canvas_size[1] * zoom}


@dataclass
class QueryMap:
    """Per-session resolved-mapping store (``query_map`` backing data).

    Agents resolve widgets/canvas rects once and reference entries by id
    instead of re-resolving every turn.

    :param session_id: Owning session.
    """

    session_id: str
    _entries: dict[str, dict[str, Any]] = field(default_factory=dict)
    _counter: int = 0

    def put(self, kind: str, payload: dict[str, Any]) -> str:
        """Store a resolved mapping, returning its entry id.

        :param kind: Entry kind (``"widget"`` or ``"canvas_rect"``).
        :param payload: Resolved mapping (rects, ids — text already
            scrubbed by the caller where needed).
        :returns: Entry id (``f"qm_{n}"``).
        """
        self._counter += 1
        entry_id = f"qm_{self._counter}"
        self._entries[entry_id] = {"id": entry_id, "kind": kind, **payload}
        return entry_id

    def get(self, entry_id: str) -> dict[str, Any] | None:
        """Return an entry, or ``None`` if unknown.

        :param entry_id: Entry id from :meth:`put`.
        """
        return self._entries.get(entry_id)


class PerceptionTools:
    """Perception tool implementations (auth + roots + backends).

    :param backend_manager: Owns per-app backends (real or fake).
    :param sessions: Session registry for roots confinement.
    :param auth_store: Token registry for direct-call allowlist checks.
    """

    def __init__(
        self,
        backend_manager: BackendManager,
        sessions: SessionRegistry | None = None,
        auth_store: AuthStore | None = None,
    ) -> None:
        self._backends = backend_manager
        self._sessions = sessions
        self._auth = auth_store
        self._query_maps: dict[str, QueryMap] = {}

    def query_map(self, session_id: str) -> QueryMap:
        """Return (creating) the session's :class:`QueryMap`.

        :param session_id: Session id.
        """
        existing = self._query_maps.get(session_id)
        if existing is None:
            existing = QueryMap(session_id)
            self._query_maps[session_id] = existing
        return existing

    def _check(
        self, tool: str, raw_token: str | None, user_id: str, session_id: str
    ) -> None:
        """Allowlist check + ingress log for direct (non-MCP) calls.

        :param tool: Tool name being invoked.
        :param raw_token: Presented bearer token (None skips the check —
            MCP-path calls are enforced by ``AuthMiddleware``).
        :param user_id: Caller id (logging only).
        :param session_id: Session id (logging only).
        :raises ToolError: Token invalid or tool not in its allowlist.
        """
        if raw_token is None:
            return
        if self._auth is None:
            raise ToolError("access denied")
        from .auth import AuthError

        try:
            record = self._auth.authenticate(raw_token)
            self._auth.authorize(record, tool)
        except AuthError:
            raise ToolError("access denied") from None
        log_tool_ingress(
            log,
            tool=tool,
            user_id=user_id,
            session_id=session_id,
            key_id=record.key_id,
        )

    async def craft_widgets(
        self,
        *,
        app: str,
        query: str = "",
        role: str = "",
        focused: bool | None = None,
        limit: int = 500,
        user_id: str = "local",
        session_id: str = "default",
        raw_token: str | None = None,
    ) -> dict[str, Any]:
        """List addressable UI widgets (pdfcraft AccessKit-via-MCP reference).

        Proxies the backend widget tree (``ui.widgets`` / ``ui_widgets`` /
        control-call passthrough when offered; canned reference shape on
        fakes) with pdfcraft AccessKit filter semantics.

        :param app: App id.
        :param query: Substring filter over label/value/description.
        :param role: Exact role filter (empty = all).
        :param focused: Focus-state filter (None = all).
        :param limit: Max widgets (default 500, per upstream).
        :param user_id: Caller id (logging only).
        :param session_id: Session id (logging only).
        :param raw_token: Bearer token for direct-call allowlist check.
        :returns: ``{app, widgets, count, truncated, query_map_ids}`` —
            widget text fields intact for the caller; logs carry structure
            only (see :func:`redact_widgets`).
        :raises ToolError: Auth failure or unknown app.
        """
        self._check("craft_widgets", raw_token, user_id, session_id)
        from .tools_phase1 import APP_REGISTRY

        if app not in APP_REGISTRY:
            raise ToolError(f"unknown app: {app}")
        backend = await self._backend_or_raise(app)
        raw_widgets = await self._fetch_widgets(backend, app)
        kept, truncated = filter_widgets(
            raw_widgets, query=query, role=role, focused=focused, limit=limit
        )
        qm = self.query_map(session_id)
        ids = [
            qm.put(
                "widget", {"app": app, "widget_id": w.get("id"), "rect": w.get("rect")}
            )
            for w in kept
            if isinstance(w, dict)
        ]
        log.info(
            "widgets listed: %s",
            safe_event(
                event="widgets_list",
                tool="craft_widgets",
                app=app,
                session_id=session_id,
                user_id=user_id,
                count=len(kept),
                ok=True,
            ),
        )
        return {
            "app": app,
            "widgets": kept,
            "count": len(kept),
            "truncated": truncated,
            "query_map_ids": ids,
        }

    async def craft_map(
        self,
        *,
        app: str,
        direction: str,
        point: list[float],
        zoom: float = 1.0,
        centre: list[float] | None = None,
        view_size: list[float] | None = None,
        canvas_size: list[float] | None = None,
        user_id: str = "local",
        session_id: str = "default",
        raw_token: str | None = None,
    ) -> dict[str, Any]:
        """Resolve document↔screen coordinates (photocraft canvasRect synthesis).

        :param app: App id (mapping is app-agnostic math; recorded per app).
        :param direction: ``"doc_to_screen"``, ``"screen_to_doc"``, or
            ``"canvas_rect"`` (derive the canvas rect from view state).
        :param point: ``[x, y]`` input point (ignored for ``canvas_rect``).
        :param zoom: View zoom factor (> 0).
        :param centre: Document-space view centre (default origin).
        :param view_size: ``[w, h]`` view size in screen points
            (default 1024×768).
        :param canvas_size: ``[w, h]`` document size in pixels (required
            for ``canvas_rect``).
        :param user_id: Caller id (logging only).
        :param session_id: Session id (logging only).
        :param raw_token: Bearer token for direct-call allowlist check.
        :returns: ``{app, direction, result, query_map_id}`` where result is
            ``[x, y]`` for point mappings or ``{x, y, w, h}`` for
            ``canvas_rect``.
        :raises ToolError: Bad direction/shape/zoom, or auth failure.
        """
        self._check("craft_map", raw_token, user_id, session_id)
        from .tools_phase1 import APP_REGISTRY

        if app not in APP_REGISTRY:
            raise ToolError(f"unknown app: {app}")
        if direction not in ("doc_to_screen", "screen_to_doc", "canvas_rect"):
            raise ToolError(f"unknown direction: {direction}")
        centre_t = (centre[0], centre[1]) if centre else (0.0, 0.0)
        view_t = (view_size[0], view_size[1]) if view_size else (1024.0, 768.0)
        try:
            if direction == "canvas_rect":
                if not canvas_size:
                    raise ToolError("canvas_rect requires canvas_size")
                result: Any = synthesize_canvas_rect(
                    zoom=zoom,
                    centre=centre_t,
                    canvas_size=(canvas_size[0], canvas_size[1]),
                    view_size=view_t,
                )
            else:
                if len(point) != 2:
                    raise ToolError("point must be [x, y]")
                fn = doc_to_screen if direction == "doc_to_screen" else screen_to_doc
                mapped = fn(
                    (point[0], point[1]),
                    zoom=zoom,
                    centre=centre_t,
                    view_size=view_t,
                )
                result = [mapped[0], mapped[1]]
        except ValueError as exc:
            raise ToolError(str(exc)) from None
        entry_id = self.query_map(session_id).put(
            "canvas_rect" if direction == "canvas_rect" else "mapping",
            {"app": app, "direction": direction, "result": result},
        )
        log.info(
            "map resolved: %s",
            safe_event(
                event="map_resolve",
                tool="craft_map",
                app=app,
                session_id=session_id,
                user_id=user_id,
                ok=True,
            ),
        )
        return {
            "app": app,
            "direction": direction,
            "result": result,
            "query_map_id": entry_id,
        }

    async def _fetch_widgets(self, backend: Any, app: str) -> list[dict[str, Any]]:
        """Fetch the raw widget tree from a backend, best-effort.

        Tries ``ui.widgets`` / ``ui_widgets`` / ``accesskit_tree`` in order;
        falls back to a canned reference shape documenting the pdfcraft
        AccessKit contract (gateway shim fallback per TC-C-01).

        :param backend: Connected app backend.
        :param app: App id (logging only).
        :returns: Raw widget mappings (unscrubbed — scrub at the log edge).
        """
        for method in ("ui.widgets", "ui_widgets", "accesskit_tree"):
            try:
                tools = await backend.list_tools()
                if method in tools:
                    payload = await backend.call_tool(method, {})
                    if isinstance(payload, dict) and isinstance(
                        payload.get("widgets"), list
                    ):
                        return [w for w in payload["widgets"] if isinstance(w, dict)]
            except BackendError:
                continue
            except Exception as exc:  # noqa: BLE001 — next candidate method
                log.debug(
                    "widgets probe failed: %s",
                    safe_event(event="widgets_probe", app=app, method=method, ok=False),
                )
                _ = exc
                continue
        log.info(
            "widgets fallback: %s",
            safe_event(
                event="widgets_fallback", tool="craft_widgets", app=app, ok=True
            ),
        )
        return _canned_widgets(app)

    async def _backend_or_raise(self, app: str) -> Any:
        try:
            return await self._backends.backend(app)
        except BackendError as exc:
            raise ToolError(str(exc)) from None


def _canned_widgets(app: str) -> list[dict[str, Any]]:
    """Canned widget tree documenting the pdfcraft AccessKit contract.

    Used when the backend offers no widget method (all fakes): the shape —
    ``{id, role, depth, enabled, clickable, focusable, label, value,
    description, rect, toggled, selected, focused}`` — is the contract
    upstream PRs must satisfy.

    :param app: App id.
    """
    _ = app
    return [
        {
            "id": "toolbar.save",
            "role": "button",
            "depth": 2,
            "enabled": True,
            "clickable": True,
            "focusable": True,
            "label": "Save",
            "value": "",
            "description": "Save the current document",
            "rect": [8, 8, 64, 32],
            "toggled": False,
            "selected": False,
            "focused": False,
        },
        {
            "id": "panel.layers",
            "role": "list",
            "depth": 3,
            "enabled": True,
            "clickable": False,
            "focusable": True,
            "label": "Layers",
            "value": "3 items",
            "description": "Document layer list",
            "rect": [8, 48, 200, 300],
            "toggled": False,
            "selected": False,
            "focused": True,
        },
        {
            "id": "dialog.export.confirm",
            "role": "button",
            "depth": 4,
            "enabled": False,
            "clickable": False,
            "focusable": False,
            "label": "Export",
            "value": "",
            "description": "Export disabled until a document is open",
            "rect": [300, 400, 120, 36],
            "toggled": False,
            "selected": False,
            "focused": False,
        },
    ]


def register_perception_tools(
    mcp: FastMCP,
    *,
    backend_manager: BackendManager,
    sessions: SessionRegistry | None = None,
    auth_store: AuthStore | None = None,
) -> PerceptionTools:
    """Wire ``craft_widgets`` + ``craft_map`` into a gateway FastMCP app.

    :param mcp: Gateway app (from ``create_gateway``).
    :param backend_manager: App backend owner.
    :param sessions: Session registry (query maps are session-scoped).
    :param auth_store: Token registry (tools re-check for direct-call safety;
        the MCP path is enforced by ``AuthMiddleware``).
    :returns: The bound :class:`PerceptionTools`.
    """
    impl = PerceptionTools(backend_manager, sessions, auth_store)

    @mcp.tool(
        name="craft_widgets",
        description="List addressable UI widgets (AccessKit reference).",
    )
    async def _craft_widgets(
        app: str,
        query: str = "",
        role: str = "",
        focused: bool | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        return await impl.craft_widgets(
            app=app, query=query, role=role, focused=focused, limit=limit
        )

    @mcp.tool(
        name="craft_map",
        description="Resolve document<->screen coordinates (canvasRect synthesis).",
    )
    async def _craft_map(
        app: str,
        direction: str,
        point: list[float] | None = None,
        zoom: float = 1.0,
        centre: list[float] | None = None,
        view_size: list[float] | None = None,
        canvas_size: list[float] | None = None,
    ) -> dict[str, Any]:
        return await impl.craft_map(
            app=app,
            direction=direction,
            point=point or [0.0, 0.0],
            zoom=zoom,
            centre=centre,
            view_size=view_size,
            canvas_size=canvas_size,
        )

    mcp.perception = impl  # type: ignore[attr-defined]
    log.info(
        "perception registered: %s",
        safe_event(event="perception_registered", count=len(TOOL_NAMES), ok=True),
    )
    return impl


__all__ = [
    "TOOL_NAMES",
    "PerceptionTools",
    "QueryMap",
    "doc_to_screen",
    "filter_widgets",
    "redact_widgets",
    "register_perception_tools",
    "screen_to_doc",
    "synthesize_canvas_rect",
]
