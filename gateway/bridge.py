"""Loopback control-channel bridge client (Lane 3, bridge mode).

Speaks the apps' de-facto control protocol over loopback TCP (see
``project_management/_templates/raw_Repository_findings/01-RESEARCH-FINDINGS.md``
§5 and each app repo's ``docs/control-protocol.md``):

- gridcraft-family (no auth): one ``{"id","method","params"}`` line in, one
  ``{"id","ok","result"|"error"}`` line out. ``gridcraft --control 7979``.
- photocraft (bearer token): an auth frame first on every connection —
  ``{"id":"auth","method":"auth","params":{"token":"<64 hex chars>"}}`` —
  then the same JSON-lines exchange. ``photocraft --control 7878
  --control-token-file <path>``. The token travels via file/env, never on
  the command line, and is never logged here.

:class:`BridgeClient` is the smallest possible path: connect (auth when a
token is configured) → ``call(method, params)`` → reply dict. Stale reply
lines (ids that do not match the in-flight request, e.g. late answers to
timed-out calls) are skipped, mirroring the upstream MCP bridges. Only
loopback destinations are dialled; anything else raises :class:`BridgeError`.

Transport ceilings mirror the documented desktop limits: 1 MiB max request
line, 8 MiB max reply, and a default 55 s call timeout (strictly below the
desktop's 60 s UI wait, so the bridge's error is what the caller sees).

SW-REQ: bridge-mode passthrough (Lane 3).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Max encoded request line (desktop enforces 1 MiB; gridcraft allows more,
#: but 1 MiB keeps every app safe).
REQUEST_MAX_BYTES = 1_048_576

#: Max encoded reply line (desktop enforces 8 MiB).
REPLY_MAX_BYTES = 8_388_608

#: Default call timeout — strictly below the desktop's 60 s UI wait.
DEFAULT_TIMEOUT_S = 55.0

#: PNG file signature (used to recognise screenshot bytes in a reply).
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

#: Reply keys searched first for screenshot payloads (base64 PNG).
_SCREENSHOT_KEYS = ("base64", "image", "png", "data", "screenshot")


class BridgeError(Exception):
    """Control-channel failure (connect/auth/protocol/timeout, safe message)."""


@dataclass
class BridgeConfig:
    """How to reach one running desktop app's control channel.

    :param app: App id (e.g. ``"gridcraft"``).
    :param host: Loopback host (anything non-loopback is refused).
    :param port: Control port the app was started with (``--control PORT``).
    :param token: Bearer token (photocraft-style auth). Prefer
        ``token_file``; a directly supplied token must never be logged.
    :param token_file: Path to a file holding the bearer token
        (``--control-token-file`` output).
    :param inspect_style: ``"direct"`` sends ``document.inspect`` (gridcraft
        family); ``"engine"`` sends ``engine.execute
        {"command": "document.inspect"}`` (photocraft family).
    :param timeout_s: Per-call timeout (default 55 s, below the desktop's
        60 s UI wait).
    """

    app: str
    host: str = "127.0.0.1"
    port: int = 7979
    token: str | None = None
    token_file: str | None = None
    inspect_style: str = "direct"
    timeout_s: float = DEFAULT_TIMEOUT_S

    def resolve_token(self) -> str | None:
        """Return the bearer token (file wins over inline), or None.

        :returns: Token string, or None when no auth is configured.
        :raises BridgeError: Token file unreadable.
        """
        if self.token_file:
            try:
                return Path(self.token_file).read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise BridgeError("control token file unreadable") from exc
        if self.token:
            return self.token
        return None


def bridges_from_env(apps: tuple[str, ...] = ("photocraft", "pdfcraft", "gridcraft")) -> dict[str, BridgeConfig]:
    """Build bridge configs from ``CRAFTER_BRIDGE_<APP>`` env vars.

    Each var holds ``host:port`` (only exact ``CRAFTER_BRIDGE_<UPPER APP>``
    names are read, e.g. ``CRAFTER_BRIDGE_GRIDCRAFT``). Optional
    ``CRAFTER_BRIDGE_<APP>_TOKEN_FILE`` supplies the bearer-token path for
    token-authed apps (photocraft). Apps without the env var are absent
    from the mapping (headless/CLI path unchanged).

    :param apps: App ids to probe for.
    :returns: App id → :class:`BridgeConfig` for every var that is set.
    """
    import os

    configs: dict[str, BridgeConfig] = {}
    for app in apps:
        env_name = f"CRAFTER_BRIDGE_{app.upper()}"
        endpoint = os.environ.get(env_name, "")
        if not endpoint:
            continue
        host, _, port_s = endpoint.rpartition(":")
        if not host or not port_s.isdigit():
            raise BridgeError(f"bad bridge endpoint in {env_name} (want host:port)")
        token_file = os.environ.get(f"{env_name}_TOKEN_FILE") or None
        configs[app] = BridgeConfig(
            app=app,
            host=host,
            port=int(port_s),
            token_file=token_file,
            inspect_style="engine" if app == "photocraft" else "direct",
        )
    return configs


def _require_loopback(host: str) -> None:
    """Reject non-loopback dial targets (the protocol is unencrypted).

    :param host: Dial host.
    :raises BridgeError: Not a loopback address.
    """
    if host == "localhost":
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise BridgeError("bridge target must be loopback")


def _png_size(raw: bytes) -> tuple[int, int] | None:
    """Parse PNG width/height from the IHDR chunk (no image dependency).

    :param raw: Candidate decoded bytes.
    :returns: ``(width, height)``, or None when not a PNG.
    """
    if len(raw) >= 24 and raw[:8] == _PNG_MAGIC and raw[12:16] == b"IHDR":
        return (
            int.from_bytes(raw[16:20], "big"),
            int.from_bytes(raw[20:24], "big"),
        )
    return None


def summarize_screenshot(app: str, reply: dict[str, Any]) -> dict[str, Any]:
    """Reduce a ``ui.screenshot`` control reply to log-safe metadata.

    Finds the base64 PNG payload (preferred keys first, then any string
    value that decodes to PNG bytes), hashes it, and parses its pixel size.
    When no image bytes are present (e.g. the app wrote ``path`` instead),
    the canonical reply JSON is hashed so ``content_hash`` still diffs
    across renders. Image bytes never leave this function.

    :param app: App id.
    :param reply: Decoded ``result`` of ``ui.screenshot``.
    :returns: ``{app, content_hash, source, width?, height?}`` with
        ``source`` always ``"bridge-window"``.
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
        if _png_size(raw) is None and not raw.startswith(_PNG_MAGIC):
            continue
        digest = hashlib.sha256(raw).hexdigest()
        meta: dict[str, Any] = {
            "app": app,
            "content_hash": f"sha256:{digest}",
            "source": "bridge-window",
        }
        size = _png_size(raw)
        if size is not None:
            meta["width"], meta["height"] = size
        return meta
    digest = hashlib.sha256(
        json.dumps(reply, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {"app": app, "content_hash": f"sha256:{digest}", "source": "bridge-window"}


class BridgeClient:
    """One authenticated loopback control connection (JSON-lines over TCP).

    Calls are serialised with a lock (one in-flight request, like the
    upstream MCP bridges). Reconnect with :meth:`connect` after :meth:`close`.

    :param config: Dial/auth parameters.
    """

    def __init__(self, config: BridgeConfig) -> None:
        self._config = config
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self._ids = itertools.count(1)

    @property
    def connected(self) -> bool:
        """Whether the TCP connection is currently open."""
        return self._writer is not None

    async def connect(self) -> None:
        """Dial the app and run the auth frame when a token is configured.

        :raises BridgeError: Non-loopback target, dial failure, or auth
            rejection (wrong/missing token).
        """
        _require_loopback(self._config.host)
        if self._writer is not None:
            return
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    self._config.host,
                    self._config.port,
                    # Default StreamReader cap is 64 KiB — real replies
                    # (window screenshots) are bigger. Cap at the documented
                    # 8 MiB desktop ceiling instead; anything larger is
                    # rejected per-line in call().
                    limit=REPLY_MAX_BYTES + 1,
                ),
                timeout=self._config.timeout_s,
            )
        except (OSError, asyncio.TimeoutError) as exc:
            raise BridgeError(
                f"cannot connect to {self._config.app} control channel"
            ) from exc
        self._reader, self._writer = reader, writer
        token = self._config.resolve_token()
        if token is not None:
            frame = json.dumps(
                {"id": "auth", "method": "auth", "params": {"token": token}},
                separators=(",", ":"),
            )
            await self._send_line(frame)
            reply = await self._read_line()
            if not isinstance(reply, dict) or reply.get("ok") is not True:
                await self.close()
                raise BridgeError("control auth rejected")

    async def close(self) -> None:
        """Close the connection (idempotent)."""
        writer, self._writer = self._writer, None
        self._reader = None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, asyncio.TimeoutError):
                pass

    async def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send one control call, return the ``result`` payload.

        Lines with non-matching ids are skipped (stale replies to earlier
        timed-out calls, as the upstream bridges do).

        :param method: Control-protocol method (e.g. ``"ui.inspect"``).
        :param params: Method params (default ``{}``).
        :returns: The reply's ``result`` (``{}`` when absent but ``ok``).
        :raises BridgeError: Not connected, oversize line, timeout, or the
            app's ``{"ok": false, "error": ...}`` (message forwarded — it
            names the method/params problem, never secrets).
        """
        if self._reader is None or self._writer is None:
            raise BridgeError("bridge not connected")
        call_id = next(self._ids)
        line = json.dumps(
            {"id": call_id, "method": method, "params": params or {}},
            separators=(",", ":"),
        )
        if len(line.encode("utf-8")) > REQUEST_MAX_BYTES:
            raise BridgeError("request exceeds 1 MiB line limit")
        async with self._lock:
            assert self._reader is not None and self._writer is not None
            await self._send_line(line)
            try:
                async with asyncio.timeout(self._config.timeout_s):
                    while True:
                        try:
                            raw = await self._reader.readline()
                        except (
                            ValueError,
                            asyncio.IncompleteReadError,
                            asyncio.LimitOverrunError,
                        ) as exc:
                            # The reply line blew past the 8 MiB ceiling
                            # (a full-window base64 screenshot does this) —
                            # honest error, never a 500.
                            raise BridgeError(
                                "reply exceeds 8 MiB limit "
                                "(screenshot to a file instead)"
                            ) from exc
                        if not raw:
                            raise BridgeError("control connection closed")
                        if len(raw) > REPLY_MAX_BYTES + 1:
                            raise BridgeError("reply exceeds 8 MiB limit")
                        try:
                            reply = json.loads(raw.decode("utf-8"))
                        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                            raise BridgeError("invalid reply line") from exc
                        if not isinstance(reply, dict) or reply.get("id") != call_id:
                            continue  # stale line for another call; skip
                        if reply.get("ok") is True:
                            result = reply.get("result", {})
                            return result if isinstance(result, dict) else {"value": result}
                        raise BridgeError(str(reply.get("error", "control call failed")))
            except TimeoutError as exc:
                raise BridgeError("control call timed out") from exc

    async def _send_line(self, line: str) -> None:
        assert self._writer is not None
        try:
            self._writer.write((line + "\n").encode("utf-8"))
            await self._writer.drain()
        except OSError as exc:
            raise BridgeError("control send failed") from exc

    async def _read_line(self) -> Any:
        assert self._reader is not None
        try:
            async with asyncio.timeout(self._config.timeout_s):
                try:
                    raw = await self._reader.readline()
                except (
                    ValueError,
                    asyncio.IncompleteReadError,
                    asyncio.LimitOverrunError,
                ) as exc:
                    raise BridgeError("reply exceeds 8 MiB limit") from exc
        except TimeoutError as exc:
            raise BridgeError("control auth timed out") from exc
        if not raw:
            raise BridgeError("control connection closed during auth")
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BridgeError("invalid auth reply") from exc


__all__ = [
    "DEFAULT_TIMEOUT_S",
    "REPLY_MAX_BYTES",
    "REQUEST_MAX_BYTES",
    "BridgeClient",
    "BridgeConfig",
    "BridgeError",
    "bridges_from_env",
    "summarize_screenshot",
]
