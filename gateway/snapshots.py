"""Session-scoped snapshot + record stores (seatbelt + evidence ledger).

- :class:`SnapshotStore` — snapshot token → app/session/revision/data-ref.
  ``restore`` returns the prior revision; tokens are unguessable secrets, so
  call sites must log only a prefix (see ``token_ref``), never the token.
- :class:`RecordStore` — session → evidence-backed claim records
  (``craft_record`` persistence).
- :func:`is_destructive_command` — auto-snapshot policy predicate shared by
  Phase-1 (``craft_run`` hook) and Phase-2 tools without import cycles.

SW-REQ: SW-REQ-GW-VERIFY (snapshot/record mechanics, TC-B-01).
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Any


class SnapshotError(Exception):
    """Unknown snapshot token, cross-session or cross-app restore attempt."""


@dataclass
class SnapshotRecord:
    """One file-level checkpoint.

    :param token: Unguessable snapshot token (``snap_<hex>``) — secret,
        never logged in full.
    :param app: App id the snapshot was taken from.
    :param session_id: Owning session (restores from other sessions are denied).
    :param user_id: User who took the snapshot.
    :param revision: Backend document revision at snapshot time — this is
        what ``restore`` returns.
    :param label: Human label (e.g. ``"auto:app.save"`` for policy snapshots).
    :param data_ref: Backend data reference (revision + content hash when the
        backend reports one); real CLIs re-open the file from this ref.
    :param created_at: Unix epoch seconds.
    """

    token: str
    app: str
    session_id: str
    user_id: str
    revision: int
    label: str = ""
    data_ref: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0

    @property
    def token_ref(self) -> str:
        """Log-safe token prefix (first 12 chars + ellipsis)."""
        return self.token[:12] + "…"


def _new_token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(16)}"


class SnapshotStore:
    """Snapshot token → app/session/revision/data-ref, keyed by session.

    Sessions never see each other's snapshots: ``restore`` fails closed on
    cross-session use with a generic message (no existence leak beyond the
    unknown-token case, which is equally generic).
    """

    def __init__(self) -> None:
        self._by_token: dict[str, SnapshotRecord] = {}

    def create(
        self,
        *,
        session_id: str,
        app: str,
        revision: int,
        user_id: str = "local",
        label: str = "",
        data_ref: dict[str, Any] | None = None,
    ) -> SnapshotRecord:
        """Take a snapshot and return its record (token is the lookup key).

        :param session_id: Owning session id.
        :param app: App id the snapshot was taken from.
        :param revision: Backend document revision at snapshot time.
        :param user_id: User who took the snapshot.
        :param label: Human label (auto-snapshot policy sets ``auto:<cmd>``).
        :param data_ref: Backend data reference for real-CLI re-open.
        :returns: The new :class:`SnapshotRecord`.
        """
        record = SnapshotRecord(
            token=_new_token("snap"),
            app=app,
            session_id=session_id,
            user_id=user_id,
            revision=int(revision),
            label=label,
            data_ref=dict(data_ref or {}),
            created_at=time.time(),
        )
        self._by_token[record.token] = record
        return record

    def get(self, token: str) -> SnapshotRecord | None:
        """Return the record for ``token``, or ``None`` if unknown.

        :param token: Snapshot token from :meth:`create`.
        """
        return self._by_token.get(token)

    def restore(self, token: str, session_id: str) -> SnapshotRecord:
        """Validate a restore and return the record holding the prior revision.

        :param token: Snapshot token from :meth:`create`.
        :param session_id: Restoring session — must own the snapshot.
        :returns: The record; callers return ``record.revision`` as
            ``restored_to`` and roll the backend back when it supports it.
        :raises SnapshotError: Unknown token, cross-session, or (checked by
            the caller) cross-app restore. Messages name no stored data.
        """
        record = self._by_token.get(token)
        if record is None:
            raise SnapshotError("unknown snapshot")
        if record.session_id != session_id:
            raise SnapshotError("access denied")
        return record

    def list_for_session(self, session_id: str) -> list[SnapshotRecord]:
        """Return all snapshots owned by ``session_id`` (oldest first).

        :param session_id: Owning session id.
        """
        return [
            record
            for record in self._by_token.values()
            if record.session_id == session_id
        ]

    def drop_session(self, session_id: str) -> int:
        """Remove every snapshot owned by ``session_id`` (session teardown).

        :param session_id: Owning session id.
        :returns: Number of snapshots removed.
        """
        doomed = [
            token
            for token, record in self._by_token.items()
            if record.session_id == session_id
        ]
        for token in doomed:
            del self._by_token[token]
        return len(doomed)


@dataclass
class RecordEntry:
    """One evidence-backed claim (``craft_record`` persistence).

    :param record_id: Public id (``rec_<hex>``) — safe to log and return.
    :param session_id: Owning session (records are session-scoped).
    :param user_id: Claiming user.
    :param claim: Claim text (stored, never logged — may carry PII).
    :param confidence: ``"measured"`` (evidence required) or ``"inferred"``.
    :param evidence: Validated evidence refs (render/assert/resource/
        snapshot/revision).
    :param note: Optional free-text note (stored, never logged).
    :param created_at: Unix epoch seconds.
    """

    record_id: str
    session_id: str
    user_id: str
    claim: str
    confidence: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    note: str = ""
    created_at: float = 0.0


class RecordStore:
    """Session → claim records. Validation lives in the tool layer (it must
    raise ``ToolError``); this store is dumb persistence."""

    def __init__(self) -> None:
        self._records: list[RecordEntry] = []

    def create(
        self,
        *,
        session_id: str,
        user_id: str,
        claim: str,
        confidence: str,
        evidence: list[dict[str, Any]],
        note: str = "",
    ) -> RecordEntry:
        """Persist a validated claim and return its entry.

        :param session_id: Owning session id.
        :param user_id: Claiming user.
        :param claim: Already-validated non-empty claim text.
        :param confidence: Already-validated ``measured``/``inferred``.
        :param evidence: Already-validated evidence refs.
        :param note: Optional note.
        :returns: The new :class:`RecordEntry`.
        """
        entry = RecordEntry(
            record_id=_new_token("rec"),
            session_id=session_id,
            user_id=user_id,
            claim=claim,
            confidence=confidence,
            evidence=[dict(item) for item in evidence],
            note=note,
            created_at=time.time(),
        )
        self._records.append(entry)
        return entry

    def list_for_session(self, session_id: str) -> list[RecordEntry]:
        """Return all records owned by ``session_id`` (oldest first).

        :param session_id: Owning session id.
        """
        return [entry for entry in self._records if entry.session_id == session_id]


# --- auto-snapshot policy ----------------------------------------------------

#: Command-name stems treated as destructive (data loss on re-run). Snapshots
#: are cheap insurance, so this list errs on the side of snapshotting.
DESTRUCTIVE_STEMS = frozenset(
    {
        "save",
        "saveas",
        "delete",
        "remove",
        "clear",
        "reset",
        "overwrite",
        "replace",
        "flatten",
        "merge",
        "crop",
        "destroy",
        "wipe",
    }
)

#: Param keys that may hold a multi-step batch (spec C1: auto-snapshot before
#: any batch with >1 destructive step).
BATCH_KEYS = ("steps", "batch", "commands", "actions")


def _stem(command: str) -> str:
    return command.strip().lower().split(".")[-1].split(":")[-1]


def is_destructive_command(command: str, params: dict[str, Any] | None) -> bool:
    """Auto-snapshot policy predicate: does this call risk data loss?

    True when the command-name stem is destructive (``app.save``,
    ``delete``, …) or when ``params`` carries a batch (``steps``/``batch``/
    ``commands``/``actions``) with more than one destructive step. Pure reads
    (``doc_inspect``, ``render_preview``, ``ui.inspect``) return False.

    :param command: Engine command name.
    :param params: Command params (scanned for nested batches only — never
        logged or mutated here).
    :returns: True when the caller should snapshot first.
    """
    if _stem(command) in DESTRUCTIVE_STEMS:
        return True
    for key in BATCH_KEYS:
        steps = (params or {}).get(key)
        if isinstance(steps, list):
            destructive = sum(
                1
                for step in steps
                if isinstance(step, dict)
                and _stem(str(step.get("command", ""))) in DESTRUCTIVE_STEMS
            )
            if destructive > 1:
                return True
    return False


__all__ = [
    "BATCH_KEYS",
    "DESTRUCTIVE_STEMS",
    "RecordEntry",
    "RecordStore",
    "SnapshotError",
    "SnapshotRecord",
    "SnapshotStore",
    "is_destructive_command",
]
