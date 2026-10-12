"""Phase-2 verification tools: craft_look, craft_snapshot/restore, record, assert.

Contracts (per 08-REQUIRED-TOOLS.md Phase 2 + §A1/C1/C2/D1):

- ``craft_look(app, scope?, index?, region?, max_side?, detail?, layer?,
  path?)`` — unified render. Returns metadata only (revision + content hash);
  image bytes never cross the gateway and never reach logs.
- ``craft_snapshot(app, label?)`` → ``{"token", "revision"}`` — file-level
  checkpoint in the session asset store (:class:`SnapshotStore`).
- ``craft_restore(app, token)`` → ``{"restored_to"}`` — prior revision;
  cross-session restores are denied, cross-app restores are rejected.
- ``craft_record(claim, confidence, evidence?, note?)`` — evidence-backed
  claims. ``confidence="measured"`` with empty evidence is **rejected**.
- ``craft_assert(app, expect, tolerance?)`` — declarative postconditions.
  Structural asserts are the default; visual asserts are opt-in and require
  an explicit tolerance (inline ``within`` or the ``tolerance`` arg).

Every tool enforces the caller's allowlist (same ``_check`` pattern as
Phase-1: the ``AuthMiddleware`` is primary, tools re-check for direct-call
safety), confines file params to session roots, and logs ingress/egress
through the project logger with renders referenced by hash/id only.

SW-REQ: SW-REQ-GW-VERIFY (verification tool surface, TC-B-01).
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from .auth import AuthStore, check_tool_allowed
from .backends import BackendError, BackendManager, SessionRegistry
from .logger import get_logger, log_tool_ingress, safe_event
from .snapshots import RecordStore, SnapshotError, SnapshotStore

log = get_logger()

TOOL_NAMES = (
    "craft_look",
    "craft_snapshot",
    "craft_restore",
    "craft_record",
    "craft_assert",
)

LOOK_SCOPES = ("content", "window", "region", "outline", "contact_sheet")
LOOK_DETAILS = ("thumbnail", "normal", "full")

CONFIDENCES = ("measured", "inferred")

EVIDENCE_KINDS = ("render", "assert", "resource", "snapshot", "revision")

#: Backend result keys safe to forward to the caller (metadata only — image
#: bytes, documents and transcripts never cross the gateway in Phase-2).
LOOK_SAFE_KEYS = (
    "app",
    "revision",
    "content_hash",
    "width",
    "height",
    "cost_tokens",
    "source",
)


def _require_app(app: str) -> None:
    """Raise a safe ``ToolError`` for unknown app ids.

    :param app: App id.
    :raises ToolError: Unknown app (message names the app id only).
    """
    from .tools_phase1 import APP_REGISTRY

    if app not in APP_REGISTRY:
        raise ToolError(f"unknown app: {app}")


class Phase2Tools:
    """Phase-2 verification tool implementations (auth + roots + backends).

    :param backend_manager: Owns per-app backends (real or fake).
    :param sessions: Session registry for roots confinement.
    :param auth_store: Token registry for direct-call allowlist checks.
    :param snapshots: Snapshot store (created fresh if omitted).
    :param records: Record store (created fresh if omitted).
    """

    def __init__(
        self,
        backend_manager: BackendManager,
        sessions: SessionRegistry | None = None,
        auth_store: AuthStore | None = None,
        snapshots: SnapshotStore | None = None,
        records: RecordStore | None = None,
    ) -> None:
        self._backends = backend_manager
        self._sessions = sessions
        self._auth = auth_store
        self._snapshots = snapshots or SnapshotStore()
        self._records = records or RecordStore()

    @property
    def snapshots(self) -> SnapshotStore:
        """The snapshot store (shared with the ``craft_run`` hook)."""
        return self._snapshots

    @property
    def records(self) -> RecordStore:
        """The record store (``craft_record`` persistence)."""
        return self._records

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

    async def craft_look(
        self,
        *,
        app: str,
        scope: str = "content",
        index: int | None = None,
        region: list[float] | None = None,
        max_side: int = 1024,
        detail: str = "normal",
        layer: str | None = None,
        path: str | None = None,
        user_id: str = "local",
        session_id: str = "default",
        raw_token: str | None = None,
    ) -> dict[str, Any]:
        """Unified render of an app document (metadata only, no pixels).

        :param app: App id.
        :param scope: One of content/window/region/outline/contact_sheet.
        :param index: Document/page/slide index.
        :param region: Document-coords rect ``[x, y, w, h]`` (4 numbers).
        :param max_side: Long-edge cap, clamped to 16..4096.
        :param detail: thumbnail/normal/full (cost ladder — default normal).
        :param layer: Render one layer in isolation.
        :param path: Also write the render to disk (confined to session roots).
        :param user_id: Caller id (logging only).
        :param session_id: Session id for roots confinement.
        :param raw_token: Bearer token for direct-call allowlist check.
        :returns: ``{"app", "scope", "detail", "revision", "content_hash",
            ...}`` — the hash (not pixels) is what enables caching/diffing.
        :raises ToolError: Unknown app, bad scope/detail/region, roots escape.
        """
        self._check("craft_look", raw_token, user_id, session_id)
        _require_app(app)
        if scope not in LOOK_SCOPES:
            raise ToolError(f"unknown scope: {scope}")
        if detail not in LOOK_DETAILS:
            raise ToolError(f"unknown detail: {detail}")
        if index is not None and (not isinstance(index, int) or index < 0):
            raise ToolError("index must be a non-negative integer")
        if region is not None and (
            not isinstance(region, (list, tuple))
            or len(region) != 4
            or not all(isinstance(v, (int, float)) for v in region)
        ):
            raise ToolError("region must be [x, y, w, h]")
        side = max(16, min(4096, int(max_side)))
        confined_path = (
            self._confine_path(session_id, path) if path is not None else None
        )
        backend = await self._backend_or_raise(app)
        try:
            result = await backend.call_tool(
                "render_preview",
                {
                    "scope": scope,
                    "index": index,
                    "region": list(region) if region is not None else None,
                    "max_side": side,
                    "detail": detail,
                    "layer": layer,
                    "path": confined_path,
                },
            )
        except BackendError as exc:
            raise ToolError(str(exc)) from None
        meta = (
            {key: result[key] for key in LOOK_SAFE_KEYS if key in result}
            if isinstance(result, dict)
            else {}
        )
        meta.setdefault("app", app)
        log.info(
            "tool egress: %s",
            safe_event(
                event="tool_egress",
                tool="craft_look",
                app=app,
                revision=meta.get("revision", 0),
                content_hash=str(meta.get("content_hash", "")),
                ok=True,
            ),
        )
        return {"scope": scope, "detail": detail, **meta}

    async def craft_snapshot(
        self,
        *,
        app: str,
        label: str = "",
        user_id: str = "local",
        session_id: str = "default",
        raw_token: str | None = None,
    ) -> dict[str, Any]:
        """Checkpoint an app document into the session asset store.

        :param app: App id.
        :param label: Human label (auto-snapshot policy sets ``auto:<cmd>``).
        :param user_id: Caller id (logging only).
        :param session_id: Owning session (restores are session-scoped).
        :param raw_token: Bearer token for direct-call allowlist check.
        :returns: ``{"token", "revision", "app"}`` — the token is secret
            (log only its prefix via ``SnapshotRecord.token_ref``).
        """
        self._check("craft_snapshot", raw_token, user_id, session_id)
        _require_app(app)
        backend = await self._backend_or_raise(app)
        try:
            info = await backend.call_tool("doc_inspect", {})
        except BackendError as exc:
            raise ToolError(str(exc)) from None
        revision = int(info.get("revision", 0)) if isinstance(info, dict) else 0
        record = self._snapshots.create(
            session_id=session_id,
            app=app,
            revision=revision,
            user_id=user_id,
            label=label,
            data_ref={"revision": revision},
        )
        log.info(
            "snapshot create: %s",
            safe_event(
                event="snapshot_create",
                tool="craft_snapshot",
                app=app,
                session_id=session_id,
                user_id=user_id,
                revision=revision,
                ok=True,
            ),
        )
        return {"token": record.token, "revision": revision, "app": app}

    async def craft_restore(
        self,
        *,
        app: str,
        token: str,
        user_id: str = "local",
        session_id: str = "default",
        raw_token: str | None = None,
    ) -> dict[str, Any]:
        """Restore an app document to a prior snapshot revision.

        :param app: App id (must match the snapshot's app).
        :param token: Snapshot token from :meth:`craft_snapshot`.
        :param user_id: Caller id (logging only).
        :param session_id: Restoring session — must own the snapshot.
        :param raw_token: Bearer token for direct-call allowlist check.
        :returns: ``{"restored_to", "app"}`` — the prior revision.
        :raises ToolError: Unknown token, cross-session restore (generic
            denial), or cross-app restore.
        """
        self._check("craft_restore", raw_token, user_id, session_id)
        _require_app(app)
        try:
            record = self._snapshots.restore(token, session_id)
        except SnapshotError as exc:
            raise ToolError(str(exc)) from None
        if record.app != app:
            raise ToolError("snapshot app mismatch")
        backend = await self._backend_or_raise(app)
        try:
            tools = await backend.list_tools()
            if "engine.restore" in tools:
                await backend.call_tool("engine.restore", {"revision": record.revision})
        except BackendError as exc:
            raise ToolError(str(exc)) from None
        log.info(
            "snapshot restore: %s",
            safe_event(
                event="snapshot_restore",
                tool="craft_restore",
                app=app,
                session_id=session_id,
                user_id=user_id,
                revision=record.revision,
                ok=True,
            ),
        )
        return {"restored_to": record.revision, "app": app}

    async def craft_record(
        self,
        *,
        claim: str,
        confidence: str,
        evidence: list[dict[str, Any]] | None = None,
        note: str = "",
        user_id: str = "local",
        session_id: str = "default",
        raw_token: str | None = None,
    ) -> dict[str, Any]:
        """Persist an evidence-backed claim (anti-hallucination ledger).

        :param claim: Claim text (non-empty; stored, never logged).
        :param confidence: ``measured`` (evidence required) or ``inferred``.
        :param evidence: Refs like ``{"kind": "render", "id": …}``,
            ``{"kind": "assert", "id": …}``,
            ``{"kind": "resource", "uri": …}``,
            ``{"kind": "snapshot", "token": …}``,
            ``{"kind": "revision", "revision": N}``.
        :param note: Optional free-text note (stored, never logged).
        :param user_id: Claiming user.
        :param session_id: Owning session.
        :param raw_token: Bearer token for direct-call allowlist check.
        :returns: ``{"record_id", "confidence", "evidence_count"}``.
        :raises ToolError: Empty claim, bad confidence, invalid evidence, or
            ``measured`` confidence with empty evidence (the whole point).
        """
        self._check("craft_record", raw_token, user_id, session_id)
        if not isinstance(claim, str) or not claim.strip():
            raise ToolError("claim must be non-empty")
        if confidence not in CONFIDENCES:
            raise ToolError(f"unknown confidence: {confidence}")
        items = list(evidence or [])
        if confidence == "measured" and not items:
            raise ToolError("measured claims require evidence")
        for item in items:
            _validate_evidence(item)
        entry = self._records.create(
            session_id=session_id,
            user_id=user_id,
            claim=claim.strip(),
            confidence=confidence,
            evidence=items,
            note=note,
        )
        log.info(
            "record create: %s",
            safe_event(
                event="record_create",
                tool="craft_record",
                session_id=session_id,
                user_id=user_id,
                count=len(items),
                ok=True,
            ),
        )
        return {
            "record_id": entry.record_id,
            "confidence": confidence,
            "evidence_count": len(items),
        }

    async def craft_assert(
        self,
        *,
        app: str,
        expect: dict[str, Any],
        tolerance: float | None = None,
        user_id: str = "local",
        session_id: str = "default",
        raw_token: str | None = None,
    ) -> dict[str, Any]:
        """Evaluate declarative postconditions against an app document.

        Structural asserts are the default (deterministic); visual asserts
        (``mean_luma_delta_from``, ``region_non_empty``) are opt-in and
        require an explicit tolerance — inline ``within`` or the
        ``tolerance`` arg.

        :param app: App id.
        :param expect: Assertion mapping, e.g. ``{"revision": 3}``,
            ``{"all": [{"revision": 3}, {"doc_count": 1}]}``,
            ``{"mean_luma_delta_from": {"revision": 2, "within": 0.02}}``.
        :param tolerance: Default tolerance for visual asserts (0..1).
        :param user_id: Caller id (logging only).
        :param session_id: Session id for roots confinement (``output_path``).
        :param raw_token: Bearer token for direct-call allowlist check.
        :returns: ``{"app", "passed", "observed", "assertions"}``.
        :raises ToolError: Empty/unknown assertions, visual assert without
            tolerance, or roots escape via ``output_path``.
        """
        self._check("craft_assert", raw_token, user_id, session_id)
        _require_app(app)
        if not isinstance(expect, dict) or not expect:
            raise ToolError("expect must be a non-empty mapping")
        if tolerance is not None and not (
            isinstance(tolerance, (int, float)) and 0 <= tolerance <= 1
        ):
            raise ToolError("tolerance must be between 0 and 1")
        backend = await self._backend_or_raise(app)
        try:
            info = await backend.call_tool("doc_inspect", {})
        except BackendError as exc:
            raise ToolError(str(exc)) from None
        if not isinstance(info, dict):
            info = {}
        observed: dict[str, Any] = {}
        passed = True
        for key, value in expect.items():
            ok, seen = await self._evaluate(
                backend, key, value, info, session_id, tolerance
            )
            observed[key] = seen
            passed = passed and ok
        log.info(
            "assert result: %s",
            safe_event(
                event="assert_result",
                tool="craft_assert",
                app=app,
                session_id=session_id,
                user_id=user_id,
                count=len(expect),
                ok=passed,
            ),
        )
        return {
            "app": app,
            "passed": passed,
            "observed": observed,
            "assertions": len(expect),
        }

    async def _evaluate(
        self,
        backend: Any,
        key: str,
        value: Any,
        info: dict[str, Any],
        session_id: str,
        tolerance: float | None,
    ) -> tuple[bool, Any]:
        """Evaluate one assertion key → (passed, observed value)."""
        documents = info.get("documents", [])
        if not isinstance(documents, list):
            documents = []
        if key == "revision":
            seen = info.get("revision")
            return seen == value, seen
        if key == "doc_count":
            seen = len(documents)
            return seen == value, seen
        if key == "layer_exists":
            layers: list[str] = []
            for doc in documents:
                if isinstance(doc, dict):
                    found = doc.get("layers", [])
                    if isinstance(found, list):
                        layers.extend(str(item) for item in found)
            seen = value in layers
            return seen, seen
        if key == "doc_size":
            seen = info.get("size")
            if seen is None and documents and isinstance(documents[0], dict):
                seen = documents[0].get("size")
            return seen == list(value) if seen is not None else False, seen
        if key == "export_format":
            seen = info.get("export_format")
            return seen == value, seen
        if key == "output_path":
            confined = self._confine_path(session_id, str(value))
            return True, confined
        if key == "selection_count":
            seen = info.get("selection_count")
            return (seen == value) if seen is not None else False, seen
        if key == "history_top":
            seen = info.get("history_top")
            return (seen == value) if seen is not None else False, seen
        if key == "all":
            if not isinstance(value, list) or not value:
                raise ToolError("all must be a non-empty list")
            sub_seen: dict[str, Any] = {}
            sub_passed = True
            for sub in value:
                if not isinstance(sub, dict) or len(sub) != 1:
                    raise ToolError("all entries must be single-key mappings")
                (sub_key, sub_value), _ = next(iter(sub.items())), None
                ok, seen = await self._evaluate(
                    backend, sub_key, sub_value, info, session_id, tolerance
                )
                sub_seen[sub_key] = seen
                sub_passed = sub_passed and ok
            return sub_passed, sub_seen
        if key == "mean_luma_delta_from":
            within = tolerance
            from_rev: Any = None
            if isinstance(value, dict):
                from_rev = value.get("revision")
                if value.get("within") is not None:
                    within = value["within"]
            if within is None or not (
                isinstance(within, (int, float)) and 0 <= within <= 1
            ):
                raise ToolError("visual assertions require tolerance")
            current = info.get("revision")
            # Coarse but deterministic: same revision ⇒ no change; a
            # different revision ⇒ changed. Real pixel-diff lands with
            # renderer-backed backends (documented limitation).
            delta = 0.0 if from_rev == current else 1.0
            return delta <= within, delta
        if key == "region_non_empty":
            if (
                not isinstance(value, dict)
                or not isinstance(value.get("rect"), (list, tuple))
                or len(value["rect"]) != 4
            ):
                raise ToolError("region_non_empty needs {rect: [x, y, w, h]}")
            try:
                render = await backend.call_tool(
                    "render_preview",
                    {"scope": "region", "region": list(value["rect"])},
                )
            except BackendError as exc:
                raise ToolError(str(exc)) from None
            seen = isinstance(render, dict) and bool(render.get("content_hash"))
            return seen, seen
        raise ToolError(f"unknown assertion: {key}")

    async def _backend_or_raise(self, app: str) -> Any:
        try:
            return await self._backends.backend(app)
        except BackendError as exc:
            raise ToolError(str(exc)) from None

    def _confine_path(self, session_id: str, path: str) -> str:
        """Confine one file path to session roots (generic denial).

        :param session_id: Session id whose roots apply.
        :param path: Candidate path.
        :returns: Resolved path as a string.
        :raises ToolError: Escape attempt (no filesystem details leak).
        """
        if self._sessions is None:
            return path
        from .backends import RootsViolation

        try:
            return str(self._sessions.check_path(session_id, path))
        except RootsViolation:
            raise ToolError("access denied") from None


def _validate_evidence(item: Any) -> None:
    """Validate one evidence ref (raises ``ToolError`` on shape violations).

    :param item: Candidate evidence mapping with a known ``kind`` plus at
        least one of ``id``/``uri``/``revision``/``token``.
    :raises ToolError: Malformed evidence (message names the problem only).
    """
    if not isinstance(item, dict):
        raise ToolError("evidence must be a list of mappings")
    if item.get("kind") not in EVIDENCE_KINDS:
        raise ToolError(f"unknown evidence kind: {item.get('kind')}")
    if not any(
        item.get(field) is not None for field in ("id", "uri", "revision", "token")
    ):
        raise ToolError("evidence needs id, uri, revision, or token")


def register_phase2_tools(
    mcp: FastMCP,
    *,
    backend_manager: BackendManager,
    sessions: SessionRegistry | None = None,
    auth_store: AuthStore | None = None,
    snapshots: SnapshotStore | None = None,
    records: RecordStore | None = None,
) -> Phase2Tools:
    """Wire the 5 Phase-2 verification tools into a gateway FastMCP app.

    :param mcp: Gateway app (from ``create_gateway``).
    :param backend_manager: App backend owner.
    :param sessions: Session registry for roots confinement.
    :param auth_store: Token registry (tools re-check for direct-call safety;
        the ``AuthMiddleware`` remains the primary enforcer).
    :param snapshots: Shared snapshot store (fresh one if omitted; share
        with ``register_phase1_tools`` so the ``craft_run`` auto-snapshot
        hook and ``craft_restore`` see the same tokens).
    :param records: Shared record store (fresh one if omitted).
    :returns: The :class:`Phase2Tools` implementation (also stashed as
        ``mcp.phase2``; stores as ``mcp.snapshots`` / ``mcp.records``).
    """
    impl = Phase2Tools(backend_manager, sessions, auth_store, snapshots, records)

    @mcp.tool(
        name="craft_look",
        description="Unified render of an app document (metadata + hash).",
    )
    async def _craft_look(
        app: str,
        scope: str = "content",
        index: int | None = None,
        region: list[float] | None = None,
        max_side: int = 1024,
        detail: str = "normal",
        layer: str | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        return await impl.craft_look(
            app=app,
            scope=scope,
            index=index,
            region=region,
            max_side=max_side,
            detail=detail,
            layer=layer,
            path=path,
        )

    @mcp.tool(
        name="craft_snapshot",
        description="Checkpoint an app document (returns a restore token).",
    )
    async def _craft_snapshot(app: str, label: str = "") -> dict[str, Any]:
        return await impl.craft_snapshot(app=app, label=label)

    @mcp.tool(
        name="craft_restore",
        description="Restore an app document to a snapshot revision.",
    )
    async def _craft_restore(app: str, token: str) -> dict[str, Any]:
        return await impl.craft_restore(app=app, token=token)

    @mcp.tool(
        name="craft_record",
        description="Persist an evidence-backed claim.",
    )
    async def _craft_record(
        claim: str,
        confidence: str,
        evidence: list[dict[str, Any]] | None = None,
        note: str = "",
    ) -> dict[str, Any]:
        return await impl.craft_record(
            claim=claim, confidence=confidence, evidence=evidence, note=note
        )

    @mcp.tool(
        name="craft_assert",
        description="Evaluate postconditions (structural default, visual opt-in).",
    )
    async def _craft_assert(
        app: str,
        expect: dict[str, Any],
        tolerance: float | None = None,
    ) -> dict[str, Any]:
        return await impl.craft_assert(app=app, expect=expect, tolerance=tolerance)

    mcp.phase2 = impl  # type: ignore[attr-defined]
    mcp.snapshots = impl.snapshots  # type: ignore[attr-defined]
    mcp.records = impl.records  # type: ignore[attr-defined]
    log.info(
        "phase2 tools registered: %s",
        safe_event(event="phase2_registered", count=len(TOOL_NAMES)),
    )
    return impl


__all__ = [
    "TOOL_NAMES",
    "Phase2Tools",
    "register_phase2_tools",
]
