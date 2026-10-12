"""Bearer-token auth with per-token tool allowlists and per-user denial.

Contract (for the TC-A-02 consumer):

- :class:`TokenRecord` — one bearer token: ``key_id`` (non-secret identifier),
  ``user_id`` (owner), ``allowlist`` (tool names this token may call;
  ``"*"`` grants all), ``revoked`` flag.
- :class:`AuthStore` — in-memory registry. ``register()`` adds tokens,
  ``authenticate(bearer)`` validates a presented token (constant-time compare),
  ``authorize(record, tool)`` enforces the allowlist.
- :class:`AuthMiddleware` — FastMCP middleware enforcing both on every
  ``tools/call`` and filtering ``tools/list`` to allowed tools. Denials raise
  :class:`fastmcp.exceptions.ToolError` with a generic message (no token
  material, no allowlist contents).

Per-user denial: revoking or narrowing one user's token never affects another
user's tokens — covered by ``gateway/tests/test_auth.py``.

SW-REQ: SW-REQ-GW-CORE (auth + allowlists, TC-A-01).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections.abc import Sequence
from dataclasses import dataclass, field

from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import Middleware
from fastmcp.tools.tool import Tool

from .logger import log_auth_decision

DENY_GENERIC = "access denied"
WILDCARD = "*"


@dataclass(frozen=True)
class TokenRecord:
    """A registered bearer token.

    :param key_id: Non-secret identifier safe for logs/correlation.
    :param user_id: Owning user; denials are scoped per user via this id.
    :param allowlist: Tool names this token may call; ``"*"`` allows all.
    :param revoked: Revoked tokens fail authentication.
    :param expires_at: Unix epoch seconds; 0 means no expiry.
    """

    key_id: str
    user_id: str
    allowlist: frozenset[str] = field(default_factory=frozenset)
    revoked: bool = False
    expires_at: float = 0.0


class AuthError(Exception):
    """Raised for authentication/authorization failures (no secrets inside)."""


class AuthStore:
    """In-memory bearer-token registry with allowlist enforcement.

    :param tokens: Optional initial mapping of raw token string to record.
        Raw token strings are stored only as SHA-256 hashes.
    """

    def __init__(self, tokens: dict[str, TokenRecord] | None = None) -> None:
        self._hashes: dict[str, TokenRecord] = {}
        for raw, record in (tokens or {}).items():
            self.register(raw, record)

    @staticmethod
    def _hash(raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def register(self, raw_token: str, record: TokenRecord) -> None:
        """Register a bearer token.

        :param raw_token: The secret token string (hashed on store, never
            logged — callers must not log it either).
        :param record: Owner, allowlist, expiry metadata.
        """
        self._hashes[self._hash(raw_token)] = record

    def revoke(self, key_id: str) -> bool:
        """Revoke every token registered under ``key_id``.

        :param key_id: Non-secret identifier of the token(s) to revoke.
        :returns: True if at least one token was revoked.
        """
        revoked_any = False
        for digest, record in list(self._hashes.items()):
            if record.key_id == key_id and not record.revoked:
                self._hashes[digest] = TokenRecord(
                    key_id=record.key_id,
                    user_id=record.user_id,
                    allowlist=record.allowlist,
                    revoked=True,
                    expires_at=record.expires_at,
                )
                revoked_any = True
        return revoked_any

    def authenticate(self, bearer: str | None) -> TokenRecord:
        """Validate a presented bearer token.

        :param bearer: Raw ``Authorization: Bearer <token>`` value (or the
            bare token). ``None``/empty fails closed.
        :returns: The matching :class:`TokenRecord`.
        :raises AuthError: Missing, unknown, revoked, or expired token.
            Messages are generic — they never echo token material.
        """
        if not bearer:
            raise AuthError("missing credentials")
        candidate = bearer[7:] if bearer.lower().startswith("bearer ") else bearer
        candidate = candidate.strip()
        if not candidate:
            raise AuthError("missing credentials")
        digest = self._hash(candidate)
        record = None
        for stored_digest, stored in self._hashes.items():
            if hmac.compare_digest(stored_digest, digest):
                record = stored
                break
        if record is None:
            raise AuthError("invalid credentials")
        if record.revoked:
            raise AuthError("invalid credentials")
        if record.expires_at and time.time() > record.expires_at:
            raise AuthError("credentials expired")
        return record

    def authorize(self, record: TokenRecord, tool: str) -> None:
        """Enforce the token's tool allowlist.

        :param record: Authenticated token record.
        :param tool: Requested tool name.
        :raises AuthError: Tool not in the allowlist. The message names the
            tool but never the allowlist contents.
        """
        if WILDCARD in record.allowlist or tool in record.allowlist:
            return
        raise AuthError(f"tool not allowed: {tool}")

    def mint(
        self, user_id: str, allowlist: set[str] | frozenset[str]
    ) -> tuple[str, TokenRecord]:
        """Create a fresh token for a user (testing/provisioning helper).

        :param user_id: Owning user id.
        :param allowlist: Tool names allowed (may contain ``"*"``).
        :returns: ``(raw_token, record)`` — the raw token is returned once
            and must be delivered securely; only its hash is stored.
        """
        raw = secrets.token_urlsafe(32)
        record = TokenRecord(
            key_id=f"key_{secrets.token_hex(4)}",
            user_id=user_id,
            allowlist=frozenset(allowlist),
        )
        self.register(raw, record)
        return raw, record


def extract_bearer(headers: dict[str, str] | None) -> str | None:
    """Extract the bearer token from HTTP headers.

    :param headers: Lower-cased header mapping (as from
        ``get_http_headers()``). ``None`` yields ``None``.
    :returns: The raw token string, or ``None`` if absent.
    """
    if not headers:
        return None
    auth = headers.get("authorization")
    if not auth:
        return None
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


class AuthMiddleware(Middleware):
    """FastMCP middleware enforcing bearer auth + per-token allowlists.

    On ``tools/call``: extracts the bearer token (HTTP ``Authorization``
    header; stdio clients authenticate via the ``_gateway_token`` argument
    injected by trusted local launchers), authenticates, enforces the
    allowlist, and strips ``_gateway_token`` before the tool runs. Denials
    raise :class:`ToolError` with a generic message. Every decision is logged
    to the audit logger with safe fields only.

    On ``tools/list``: returns only the tools the caller's token allows, so
    unlisted tools are not even advertised.

    :param store: The :class:`AuthStore` to enforce.
    :param require_auth: If False (tests/local stdio), requests without a
        token are allowed through with an open allowlist. Defaults True.
    """

    def __init__(self, store: AuthStore, *, require_auth: bool = True) -> None:
        self._store = store
        self._require_auth = require_auth

    def _current_record(self) -> TokenRecord | None:
        headers = get_http_headers()
        bearer = extract_bearer(headers)
        if bearer is None:
            return None
        try:
            return self._store.authenticate(bearer)
        except AuthError:
            return None

    def _decision(
        self, *, user_id: str, key_id: str, tool: str, ok: bool, error_code: str = ""
    ) -> None:
        log_auth_decision(
            user_id=user_id, tool=tool, ok=ok, key_id=key_id, error_code=error_code
        )

    async def on_call_tool(self, context, call_next):
        params = context.message
        tool_name: str = params.name
        args = dict(params.arguments or {})

        raw_token = args.pop("_gateway_token", None)
        if raw_token is None:
            record = self._current_record()
            if record is None and self._require_auth:
                headers = get_http_headers()
                if extract_bearer(headers) is None:
                    self._decision(
                        user_id="anonymous",
                        key_id="",
                        tool=tool_name,
                        ok=False,
                        error_code="missing_credentials",
                    )
                else:
                    self._decision(
                        user_id="anonymous",
                        key_id="",
                        tool=tool_name,
                        ok=False,
                        error_code="invalid_credentials",
                    )
                raise ToolError(DENY_GENERIC)
        else:
            try:
                record = self._store.authenticate(str(raw_token))
            except AuthError:
                self._decision(
                    user_id="anonymous",
                    key_id="",
                    tool=tool_name,
                    ok=False,
                    error_code="invalid_credentials",
                )
                raise ToolError(DENY_GENERIC) from None

        if record is None:
            # require_auth=False path (local stdio without a token).
            return await call_next(context.copy(message=params))

        try:
            self._store.authorize(record, tool_name)
        except AuthError:
            self._decision(
                user_id=record.user_id,
                key_id=record.key_id,
                tool=tool_name,
                ok=False,
                error_code="tool_not_allowed",
            )
            raise ToolError(DENY_GENERIC) from None

        self._decision(
            user_id=record.user_id,
            key_id=record.key_id,
            tool=tool_name,
            ok=True,
        )
        # Forward without the smuggled credential.
        stripped = params.model_copy(update={"arguments": args})
        return await call_next(context.copy(message=stripped))

    async def on_list_tools(self, context, call_next):
        tools: Sequence[Tool] = await call_next(context)
        record = self._current_record()
        if record is None:
            if self._require_auth:
                return []
            return tools
        if WILDCARD in record.allowlist:
            return tools
        return [t for t in tools if t.name in record.allowlist]

    @property
    def store(self) -> AuthStore:
        """The enforced :class:`AuthStore` (TC-A-02 uses it for tool wiring)."""
        return self._store


def check_tool_allowed(
    store: AuthStore, raw_token: str | None, tool: str
) -> TokenRecord:
    """Synchronous authenticate+authorize helper for non-MCP entry points.

    :param store: Token registry.
    :param raw_token: Presented bearer token.
    :param tool: Requested tool name.
    :returns: The authenticated record.
    :raises AuthError: On authentication or allowlist failure.
    """
    record = store.authenticate(raw_token)
    store.authorize(record, tool)
    return record
