"""Connection diagnostics: ring buffer + probes (gateway/Scaico/LiteLLM).

User requirement: "log system for ArtCraft-app/gateway, Scaico, LiteLLM
connections". This module owns that observability:

- :class:`DiagnosticsLog` — thread-safe ``deque(maxlen=200)`` of
  ``{at (epoch), service, ok, latency_ms?, detail?}`` (safe strings only;
  keys are never recorded, logged, or returned).
- Probes — one per dependency, each recording an entry and returning a
  view-safe check dict:
  - ``gateway`` — TCP connect to the configured gateway endpoint host:port.
  - ``controller`` — self check (always ok).
  - ``scaico`` — ``GET {base}/api/info`` with the stored ``X-API-Key``
    header, mirroring swaibian-one ``validate_api_key`` (headers, base
    default ``http://127.0.0.1:9000/public_api`` with
    ``SCAICO_PUBLIC_API_BASE_URL`` env override, ok on 2xx); no key
    configured → ``{ok: false, configured: false}``.
  - ``litellm`` — active profile ? ``LlmClient.ping()`` (5s timeout) :
    ``{ok: false, configured: false}``.
- :func:`probe_all` runs the four probes sequentially (each bounded ≤5s)
  and returns the ``checks`` mapping for ``GET /api/diagnostics``.

Wiring chain: ``controller.service.create_app`` → ``GET /api/diagnostics``
→ :func:`probe_all` → per-service probe → :func:`record`.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from collections import deque
from typing import Any
from urllib.parse import urlparse

import httpx

from .logger import get_logger, safe_event

log = get_logger()

MAX_ENTRIES = 200
PROBE_TIMEOUT_S = 5.0
RECENT_DEFAULT_N = 20
SCAICO_DEFAULT_BASE = "http://127.0.0.1:9000/public_api"


def scaico_base_url() -> str:
    """Scaico public-API base (env override, same default as swaibian-one).

    :returns: Base URL without trailing slash.
    """
    return (os.environ.get("SCAICO_PUBLIC_API_BASE_URL") or SCAICO_DEFAULT_BASE).rstrip(
        "/"
    )


class DiagnosticsLog:
    """Thread-safe ring buffer of connection-check entries.

    :param maxlen: Maximum retained entries (oldest evicted first).
    """

    def __init__(self, maxlen: int = MAX_ENTRIES) -> None:
        self._lock = threading.Lock()
        self._entries: deque[dict[str, Any]] = deque(maxlen=maxlen)

    def record(
        self,
        service: str,
        ok: bool,
        *,
        latency_ms: int | None = None,
        detail: str = "",
    ) -> dict[str, Any]:
        """Append a check entry (safe strings only — never pass key material).

        :param service: Dependency name (``gateway``/``controller``/``scaico``/``litellm``).
        :param ok: Whether the check succeeded.
        :param latency_ms: Measured latency (when a probe ran).
        :param detail: Short safe detail (no secrets, no content).
        :returns: The recorded entry.
        """
        entry: dict[str, Any] = {
            "at": time.time(),
            "service": str(service),
            "ok": bool(ok),
        }
        if latency_ms is not None:
            entry["latency_ms"] = int(latency_ms)
        if detail:
            entry["detail"] = str(detail)
        with self._lock:
            self._entries.append(entry)
        log.info(
            "diagnostic probe: %s",
            safe_event(
                event="diagnostic_probe",
                service=str(service),
                latency_ms=int(latency_ms) if latency_ms is not None else 0,
                ok=bool(ok),
            ),
        )
        return dict(entry)

    def recent(self, n: int = RECENT_DEFAULT_N) -> list[dict[str, Any]]:
        """Return the newest ``n`` entries, newest first.

        :param n: Maximum entries to return.
        """
        with self._lock:
            items = list(self._entries)
        items.reverse()
        return [dict(entry) for entry in items[: max(0, n)]]


DIAGNOSTICS = DiagnosticsLog()


def record(
    service: str,
    ok: bool,
    *,
    latency_ms: int | None = None,
    detail: str = "",
) -> dict[str, Any]:
    """Record an entry on the process singleton buffer (see :meth:`DiagnosticsLog.record`)."""
    return DIAGNOSTICS.record(service, ok, latency_ms=latency_ms, detail=detail)


def recent(n: int = RECENT_DEFAULT_N) -> list[dict[str, Any]]:
    """Return the newest ``n`` singleton entries, newest first."""
    return DIAGNOSTICS.recent(n)


def scaico_info(
    api_key: str, *, base_url: str | None = None, timeout: float = PROBE_TIMEOUT_S
) -> dict[str, Any]:
    """Validate a Scaico key via ``GET {base}/api/info`` (key never echoed).

    Mirrors swaibian-one ``ScaicoPublicApiClient.validate_api_key``: the key
    travels in the ``X-API-Key`` header only, ``Accept: application/json``,
    ok on 2xx; transport failures and non-2xx map to safe messages.

    :param api_key: Raw Scaico key (header only, never logged/returned).
    :param base_url: Override for the Scaico base (defaults to :func:`scaico_base_url`).
    :param timeout: HTTP timeout seconds.
    :returns: ``{ok, latency_ms?, status?, error?}`` — never includes the key.
    """
    base = (base_url or scaico_base_url()).rstrip("/")
    started = time.monotonic()
    try:
        response = httpx.get(
            f"{base}/api/info",
            headers={"Accept": "application/json", "X-API-Key": api_key},
            timeout=timeout,
        )
    except httpx.HTTPError:
        return {"ok": False, "error": "scaico unreachable"}
    latency_ms = int((time.monotonic() - started) * 1000)
    if 200 <= response.status_code < 300:
        return {"ok": True, "latency_ms": latency_ms, "status": response.status_code}
    return {
        "ok": False,
        "latency_ms": latency_ms,
        "status": response.status_code,
        "error": f"scaico answered status {response.status_code}",
    }


def probe_gateway(endpoint: str, *, timeout: float = PROBE_TIMEOUT_S) -> dict[str, Any]:
    """TCP-connect probe of the configured gateway endpoint (records an entry).

    :param endpoint: Gateway URL from settings (host:port are dialed).
    :param timeout: Connect timeout seconds.
    :returns: ``{ok, latency_ms?}`` or ``{ok: false, detail}`` (safe strings).
    """
    try:
        parts = urlparse(endpoint or "")
        host = parts.hostname or ""
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        record("gateway", False, detail="unparsable endpoint")
        return {"ok": False, "detail": "unparsable endpoint"}
    if not host:
        record("gateway", False, detail="unparsable endpoint")
        return {"ok": False, "detail": "unparsable endpoint"}
    started = time.monotonic()
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
    except OSError:
        record("gateway", False, detail="tcp connect failed")
        return {"ok": False, "detail": "tcp connect failed"}
    latency_ms = int((time.monotonic() - started) * 1000)
    record("gateway", True, latency_ms=latency_ms, detail="tcp connect ok")
    return {"ok": True, "latency_ms": latency_ms}


def probe_controller() -> dict[str, Any]:
    """Self check (records an entry; always ok).

    :returns: ``{ok: true}``.
    """
    record("controller", True, detail="self ok")
    return {"ok": True}


def probe_scaico(
    stored_key: str, *, timeout: float = PROBE_TIMEOUT_S
) -> dict[str, Any]:
    """Scaico probe: stored key ? ``GET {base}/api/info`` : not-configured.

    :param stored_key: Raw stored key (header only, never logged/returned).
    :param timeout: HTTP timeout seconds.
    :returns: ``{ok, latency_ms?}`` or ``{ok: false, configured: false}``.
    """
    if not stored_key:
        record("scaico", False, detail="no key configured")
        return {"ok": False, "configured": False}
    result = scaico_info(stored_key, timeout=timeout)
    if result["ok"]:
        record("scaico", True, latency_ms=result["latency_ms"], detail="api info ok")
        return {"ok": True, "latency_ms": result["latency_ms"]}
    record("scaico", False, detail="api info failed")
    out: dict[str, Any] = {"ok": False, "error": result["error"]}
    if result.get("latency_ms") is not None:
        out["latency_ms"] = result["latency_ms"]
    return out


def probe_litellm(
    profile: Any | None, *, timeout: float = PROBE_TIMEOUT_S
) -> dict[str, Any]:
    """LiteLLM probe: active profile ? ``LlmClient.ping()`` : not-configured.

    :param profile: Active server-side profile (includes key) or None.
    :param timeout: HTTP timeout seconds (bounded, unlike the chat path).
    :returns: ``{ok, latency_ms?, detail?}`` or ``{ok: false, configured: false}``.
    """
    from .llm import LlmClient, LlmError

    if profile is None:
        record("litellm", False, detail="no profile configured")
        return {"ok": False, "configured": False}
    started = time.monotonic()
    try:
        pinged = LlmClient(
            api_base=profile.api_base,
            api_key=profile.api_key,
            default_model=profile.default_model or "default",
            timeout_s=timeout,
        ).ping()
    except LlmError as exc:
        record("litellm", False, detail="models probe failed")
        return {"ok": False, "error": str(exc)}
    latency_ms = int((time.monotonic() - started) * 1000)
    if pinged.get("auth") == "rejected":
        record("litellm", True, latency_ms=latency_ms, detail="reachable, key rejected")
        return {
            "ok": True,
            "latency_ms": latency_ms,
            "detail": "reachable, key rejected",
        }
    record("litellm", True, latency_ms=latency_ms, detail="models reachable")
    return {"ok": True, "latency_ms": latency_ms}


def probe_all(settings: Any) -> dict[str, dict[str, Any]]:
    """Run all four probes sequentially (each bounded ≤5s) and record entries.

    :param settings: :class:`SettingsStore` (gateway endpoint, Scaico key, profile).
    :returns: ``{gateway, controller, scaico, litellm}`` check dicts.
    """
    return {
        "gateway": probe_gateway(settings.get_gateway_endpoint()),
        "controller": probe_controller(),
        "scaico": probe_scaico(settings.get_scaico_key()),
        "litellm": probe_litellm(settings.active_profile()),
    }


__all__ = [
    "DIAGNOSTICS",
    "MAX_ENTRIES",
    "PROBE_TIMEOUT_S",
    "RECENT_DEFAULT_N",
    "SCAICO_DEFAULT_BASE",
    "DiagnosticsLog",
    "probe_all",
    "probe_controller",
    "probe_gateway",
    "probe_litellm",
    "probe_scaico",
    "recent",
    "record",
    "scaico_base_url",
    "scaico_info",
]
