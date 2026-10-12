"""OpenAI-compatible chat-completions client + MockBrain fallback.

- :class:`LlmClient` — httpx client against the configured profile
  (``api_base`` + ``api_key`` + ``default_model``): ``chat()`` sends messages
  + tool schemas and parses ``tool_calls``; keys travel in the
  ``Authorization`` header only and are never logged.
- :class:`MockBrain` — deterministic rule-based planner used when no profile
  is configured: emits tool calls for edit requests (resize/rotate/cell ops,
  or live command-surface ops in live mode) so the whole agent loop works
  with no key. Every plan is labeled ``mock`` so callers (and the view) can
  show the fallback state.

SW-REQ: SW-REQ-STREAM (LiteLLM-direct-style completions path, TC-B).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .logger import get_logger, safe_event

log = get_logger()


@dataclass
class ToolCall:
    """One parsed function call from the model.

    :param name: Tool name (adapter op, e.g. ``photo.resize``).
    :param arguments: Decoded JSON arguments mapping.
    :param call_id: Provider call id (``mock_N`` for MockBrain).
    """

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str = ""


@dataclass
class LlmPlan:
    """A planner decision: reply text + tool calls + provenance.

    :param text: Assistant text (may be empty when acting purely by tools).
    :param tool_calls: Ordered tool calls to execute.
    :param mock: True when produced by :class:`MockBrain` (no key path).
    :param model: Model name that produced the plan (``"mock"`` for MockBrain).
    """

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    mock: bool = False
    model: str = ""


class LlmError(Exception):
    """LLM call failed (transport, auth, or bad payload — safe message)."""


def _upstream_error_detail(response: Any) -> str:
    """Extract a short, log-safe upstream error detail (no key material).

    Providers answer 400 with a JSON ``{error: {message}}`` or
    ``{message}`` body. Only the first 200 chars of the message/code are
    kept; anything that looks like a secret is dropped.

    :param response: httpx response with a 4xx/5xx status.
    :returns: Short detail string or ``""`` when nothing safe is present.
    """
    try:
        payload = response.json()
    except (ValueError, AttributeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    raw: Any = payload.get("error", payload.get("message", ""))
    if isinstance(raw, dict):
        raw = raw.get("message", raw.get("code", ""))
    text = str(raw or "").strip().replace("\n", " ")
    if not text:
        return ""
    lowered = text.lower()
    if any(part in lowered for part in ("api_key", "apikey", "bearer", "sk-")):
        return "upstream rejected the request"
    return text[:200]


# --- tool schemas advertised to the model ------------------------------------

AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "sheet.set_cell",
            "description": "Set a spreadsheet cell value (e.g. A1).",
            "parameters": {
                "type": "object",
                "properties": {
                    "cell": {"type": "string"},
                    "value": {"type": ["string", "number"]},
                    "sheet": {"type": "string"},
                },
                "required": ["cell", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sheet.add_sheet",
            "description": "Add a new worksheet to the workbook.",
            "parameters": {
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "photo.transform",
            "description": "Transform the photo (resize/rotate/convert/grayscale/blur).",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["resize", "rotate", "convert", "grayscale", "blur"],
                    },
                    "width": {"type": "integer"},
                    "height": {"type": "integer"},
                    "degrees": {"type": "number"},
                    "format": {"type": "string"},
                },
                "required": ["kind"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pdf.transform",
            "description": "Transform PDF pages (rotate/delete).",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["rotate", "delete"]},
                    "page": {"type": "integer"},
                    "degrees": {"type": "integer"},
                },
                "required": ["kind", "page"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "done",
            "description": "Finish the run with a summary for the user.",
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            },
        },
    },
]

#: Tool schemas for the live-app lane: the model drives the user's OPEN
#: desktop document through the app's own command/MCP surface
#: (``engine.execute``/``engine.commands``/``app.save`` on the control
#: channel). Edits are visible in the open window immediately; the user's
#: file is written only by an explicit ``doc_save``.
LIVE_APP_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "command_run",
            "description": (
                "Run one command of the open app's own command surface on the "
                "user's OPEN document — the effect is visible immediately in "
                "the app window. E.g. image.imageRotationcw rotates 90 degrees "
                "clockwise, image.imageRotationccw counter-clockwise, "
                "image.imageRotation 180 degrees, image.mode.grayscale converts "
                "to grayscale, filter.blur.gaussianBlur blurs. Discover command "
                "ids and their params with command_list first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Command id, e.g. image.imageRotationcw.",
                    },
                    "params": {
                        "type": "object",
                        "description": (
                            "Command params object (omit when the command takes "
                            "none; see command_list for each command's params)."
                        ),
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "command_list",
            "description": (
                "List the open app's full command registry (ids, labels, "
                "parameter docs, enablement) to discover its functionality. "
                "An optional filter narrows by substring."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "description": "Optional substring filter on command ids.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "doc_inspect",
            "description": (
                "Inspect the user's OPEN document in the live app (layer "
                "tree, history, dimensions) to verify what an edit did."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "doc_save",
            "description": (
                "Save the user's OPEN document. ONLY call this when the user "
                "explicitly asks to save — visible edits need no save. The "
                "optional path must be a relative path inside the app's "
                "automation write root; without path the document's own file "
                "is written back."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Optional relative target path under the app's "
                            "write root (never absolute, never ..)."
                        ),
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "look",
            "description": (
                "Capture the open app's window so you can see the current "
                "state of the user's document and verify edits visually."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "done",
            "description": "Finish the run with a summary for the user.",
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            },
        },
    },
]


class LlmClient:
    """OpenAI-compatible chat-completions client for one profile.

    :param api_base: Base URL of the ``/v1`` endpoint (trailing slash ok).
    :param api_key: Secret key (header only, never logged).
    :param default_model: Model name for ``chat`` when not overridden.
    :param timeout_s: HTTP timeout in seconds.
    """

    def __init__(
        self,
        *,
        api_base: str,
        api_key: str,
        default_model: str,
        timeout_s: float = 60.0,
    ) -> None:
        self._base = api_base.rstrip("/")
        self._key = api_key
        self._model = default_model
        self._timeout = timeout_s

    @property
    def model(self) -> str:
        """Configured default model name."""
        return self._model

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
    ) -> LlmPlan:
        """Send a chat-completions request and parse the plan.

        :param messages: OpenAI-style ``[{role, content}]`` history.
        :param tools: Tool schemas (defaults to :data:`AGENT_TOOLS`).
        :param model: Model override (defaults to the profile model).
        :returns: :class:`LlmPlan` with text + parsed tool calls.
        :raises LlmError: Transport/auth/payload failure (safe message).
        """
        body = {
            "model": model or self._model,
            "messages": messages,
            "tools": tools if tools is not None else AGENT_TOOLS,
            "tool_choice": "auto",
        }
        started = time.monotonic()
        log.info(
            "llm request: %s",
            safe_event(
                event="llm_request",
                count=len(messages),
                model=str(body["model"]),
                ok=True,
            ),
        )
        try:
            response = httpx.post(
                f"{self._base}/chat/completions",
                headers={"Authorization": f"Bearer {self._key}"},
                json=body,
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            log.warning(
                "llm transport failed: %s",
                safe_event(
                    event="llm_error",
                    model=str(body["model"]),
                    error="transport failed",
                    duration_ms=duration_ms,
                    ok=False,
                ),
            )
            raise LlmError("llm transport failed") from exc
        duration_ms = int((time.monotonic() - started) * 1000)
        if response.status_code == 401:
            log.warning(
                "llm auth rejected: %s",
                safe_event(
                    event="llm_error",
                    model=str(body["model"]),
                    status=response.status_code,
                    error="auth rejected",
                    duration_ms=duration_ms,
                    ok=False,
                ),
            )
            raise LlmError("llm auth rejected (check profile key)")
        if response.status_code >= 400:
            detail = _upstream_error_detail(response)
            suffix = f": {detail}" if detail else ""
            log.warning(
                "llm request failed: %s",
                safe_event(
                    event="llm_error",
                    model=str(body["model"]),
                    status=response.status_code,
                    error=detail or f"status {response.status_code}",
                    duration_ms=duration_ms,
                    ok=False,
                ),
            )
            raise LlmError(f"llm request failed: status {response.status_code}{suffix}")
        try:
            payload = response.json()
            message = payload["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LlmError("llm returned an unreadable payload") from exc
        calls: list[ToolCall] = []
        for raw in message.get("tool_calls") or []:
            fn = (raw.get("function") or {}) if isinstance(raw, dict) else {}
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except ValueError:
                args = {}
            if name:
                calls.append(
                    ToolCall(
                        name=str(name),
                        arguments=args if isinstance(args, dict) else {},
                        call_id=str(raw.get("id", "")),
                    )
                )
        plan = LlmPlan(
            text=str(message.get("content") or ""),
            tool_calls=calls,
            mock=False,
            model=body["model"],
        )
        log.info(
            "llm plan: %s",
            safe_event(
                event="llm_plan",
                model=str(body["model"]),
                count=len(calls),
                duration_ms=duration_ms,
                status=response.status_code,
                ok=True,
            ),
        )
        return plan

    def ping(self) -> dict[str, Any]:
        """Probe the endpoint with ``GET {base}/models`` (no key echoed).

        Any 2xx counts as connected; 401 counts as reachable-but-wrong-key
        (the endpoint speaks OpenAI, which is what the test checks).
        Network failures and other statuses return safe errors.

        :returns: ``{reachable, models?}`` — never includes the key.
        :raises LlmError: Unreachable endpoint or unexpected status.
        """
        try:
            response = httpx.get(
                f"{self._base}/models",
                headers=({"Authorization": f"Bearer {self._key}"} if self._key else {}),
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise LlmError("endpoint unreachable") from exc
        if response.status_code == 401:
            return {"reachable": True, "auth": "rejected"}
        if response.status_code >= 400:
            raise LlmError(f"endpoint answered status {response.status_code}")
        try:
            payload = response.json()
            models = [m.get("id", "") for m in payload.get("data", [])]
        except ValueError:
            models = []
        log.info(
            "llm ping: %s",
            safe_event(event="llm_ping", count=len(models), ok=True),
        )
        return {"reachable": True, "models": models[:20]}


# --- MockBrain: deterministic no-key planner ----------------------------------

_CELL_RE = re.compile(r"\b([A-Z]{1,3}[1-9][0-9]{0,5})\b")
_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)")


def _clean_sheet_value(raw: str) -> str | int | float:
    """Trim prose/punctuation off a mock-planned cell value.

    :param raw: Raw captured value text (may include trailing prose like
        "99 and tell me ..." or a sentence period "7.").
    :returns: Trimmed string, coerced to int/float when obviously numeric.
    """
    value = re.split(
        r"\s+and\s+|\s+then\s+|[,;]", raw.strip().strip("\"'"), maxsplit=1
    )[0].strip()
    if len(value) > 1 and value.endswith(".") and not value.endswith(".."):
        value = value[:-1].strip()
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d*\.\d+", value):
        return float(value)
    return value


class MockBrain:
    """Deterministic rule-based planner for the no-key path (labeled mock).

    Understands the north-star edit requests so the whole loop works without
    a configured profile:

    - ``resize to <N>px`` / ``<W>x<H>`` → ``photo.transform resize``.
    - ``rotate (page <N>) (by <D> degrees)`` → ``photo.transform`` /
      ``pdf.transform rotate``.
    - ``grayscale`` / ``black and white`` → ``photo.transform grayscale``.
    - ``blur`` → ``photo.transform blur``.
    - ``set <CELL> to <value>`` / ``make <CELL> ...`` → ``sheet.set_cell``.
    - ``add sheet <name>`` → ``sheet.add_sheet``.
    - ``delete page <N>`` → ``pdf.transform delete``.
    - Anything else → a clarifying question (no tool calls).

    Live mode (``live=True``) plans against the app's command surface
    instead of the adapters:

    - ``rotate ... clockwise`` / ``rotate 90`` → ``command_run
      image.imageRotationcw``.
    - ``rotate ... counter...`` → ``command_run image.imageRotationccw``.
    - ``rotate 180`` → ``command_run image.imageRotation``.
    - ``grayscale`` / ``black and white`` → ``command_run
      image.mode.grayscale``.
    - ``blur`` → ``command_run filter.blur.gaussianBlur {radius: 3}``.
    - ``save`` → ``doc_save``.
    - Anything else → ``done`` with a summary.
    """

    def __init__(self) -> None:
        self._counter = 0

    def _call(self, name: str, arguments: dict[str, Any]) -> ToolCall:
        self._counter += 1
        return ToolCall(name=name, arguments=arguments, call_id=f"mock_{self._counter}")

    def plan(
        self,
        message: str,
        *,
        doc_kind: str = "",
        history: str = "",
        team_id: str | None = None,
        live: bool = False,
    ) -> LlmPlan:
        """Plan tool calls for a user message (deterministic, no network).

        :param message: User message text.
        :param doc_kind: Open document kind (``sheet``/``photo``/``pdf``/``""``).
        :param history: Prior observation summary (unused — signature parity).
        :param team_id: Owning team id (prefixes the reply ``[team <id>]`` so
            the team binding is visible even on the no-key path; requirement:
            team must be behaviorally real, not just accepted).
        :param live: Plan against the live-app command surface
            (:data:`LIVE_APP_TOOLS`) instead of the document adapters.
        :returns: :class:`LlmPlan` with ``mock=True``.
        """
        _ = history
        text = message.strip()
        lowered = text.lower()
        calls: list[ToolCall] = []
        reply = ""

        # Follow-up check-in from the agent loop ("Done so far: X. Original
        # request: ..."): no more work was described, so finish with done.
        followup = re.match(
            r"Done so far:\s*(.*?)\.\s*Original request:", text, re.DOTALL
        )
        if followup:
            summary = followup.group(1).strip() or "Done."
            calls.append(self._call("done", {"summary": summary}))
            return LlmPlan(text="", tool_calls=calls, mock=True, model="mock")

        if live:
            return self._plan_live(text, lowered, team_id)

        width: int | None = None
        height: int | None = None
        wh = re.search(r"(\d{2,5})\s*[x×]\s*(\d{2,5})", lowered)
        px = re.search(r"(\d{2,5})\s*px", lowered)
        if wh:
            width, height = int(wh.group(1)), int(wh.group(2))
        elif px:
            width = int(px.group(1))

        page = 1
        page_match = re.search(r"page\s+(\d+)", lowered)
        if page_match:
            page = max(1, int(page_match.group(1)))

        degrees = 90
        deg_match = re.search(r"(\d+(?:\.\d+)?)\s*deg", lowered)
        if deg_match:
            degrees = float(deg_match.group(1))

        if "resize" in lowered:
            # Emit regardless of doc kind: the executor enforces "no document
            # open" / kind mismatch gracefully (no blind planning around it).
            args: dict[str, Any] = {"kind": "resize"}
            if width:
                args["width"] = width
            if height:
                args["height"] = height
            if "width" not in args and "height" not in args:
                args["width"] = 800
            calls.append(self._call("photo.transform", args))
            reply = "Resizing the photo copy."
        elif "rotat" in lowered:
            if doc_kind == "pdf":
                calls.append(
                    self._call(
                        "pdf.transform",
                        {"kind": "rotate", "page": page, "degrees": int(degrees)},
                    )
                )
                reply = f"Rotating page {page}."
            elif doc_kind == "photo":
                calls.append(
                    self._call(
                        "photo.transform", {"kind": "rotate", "degrees": degrees}
                    )
                )
                reply = "Rotating the photo copy."
        elif ("grayscale" in lowered or "black and white" in lowered) and doc_kind in (
            "photo",
            "",
        ):
            calls.append(self._call("photo.transform", {"kind": "grayscale"}))
            reply = "Converting the photo copy to grayscale."
        elif "blur" in lowered and doc_kind in ("photo", ""):
            calls.append(self._call("photo.transform", {"kind": "blur"}))
            reply = "Blurring the photo copy."
        elif "delete" in lowered and "page" in lowered and doc_kind == "pdf":
            calls.append(self._call("pdf.transform", {"kind": "delete", "page": page}))
            reply = f"Deleting page {page}."
        elif doc_kind == "sheet" or "cell" in lowered or _CELL_RE.search(text):
            set_match = re.search(
                r"(?:set\s+(?:cell\s+)?([A-Z]{1,3}[1-9][0-9]{0,5})\s*(?:to|=)\s*(.+))|(?:value\s+(.+?)\s+(?:in|into|at)\s+([A-Z]{1,3}[1-9][0-9]{0,5}))",
                text,
                re.IGNORECASE,
            )
            if set_match:
                cell = (set_match.group(1) or set_match.group(4) or "").upper()
                value = _clean_sheet_value(
                    set_match.group(2) or set_match.group(3) or ""
                )
                calls.append(
                    self._call("sheet.set_cell", {"cell": cell, "value": value})
                )
                reply = f"Setting {cell}."
            else:
                cell_match = _CELL_RE.search(text)
                if cell_match:
                    value_match = re.search(r"(?:to|=)\s*(.+)$", text)
                    value = _clean_sheet_value(
                        value_match.group(1) if value_match else ""
                    )
                    calls.append(
                        self._call(
                            "sheet.set_cell",
                            {"cell": cell_match.group(1).upper(), "value": value},
                        )
                    )
                    reply = f"Setting {cell_match.group(1).upper()}."
                elif "add sheet" in lowered or "new sheet" in lowered:
                    name_match = re.search(
                        r"(?:add|new)\s+sheet\s+[\"']?([\w\- ]+)[\"']?", lowered
                    )
                    title = name_match.group(1).strip() if name_match else "Sheet2"
                    calls.append(self._call("sheet.add_sheet", {"title": title}))
                    reply = f"Adding sheet {title}."
        elif "add sheet" in lowered or "new sheet" in lowered:
            name_match = re.search(
                r"(?:add|new)\s+sheet\s+[\"']?([\w\- ]+)[\"']?", lowered
            )
            title = name_match.group(1).strip() if name_match else "Sheet2"
            calls.append(self._call("sheet.add_sheet", {"title": title}))
            reply = f"Adding sheet {title}."

        if not calls and not reply:
            reply = (
                "I can edit the open document copy: resize/rotate/grayscale for "
                "photos, set cells or add sheets for spreadsheets, rotate/delete "
                "pages for PDFs. What should I change?"
            )
        if team_id:
            reply = f"[team {team_id}] {reply}"
        plan = LlmPlan(text=reply, tool_calls=calls, mock=True, model="mock")
        log.info(
            "mock plan: %s",
            safe_event(event="mock_plan", count=len(calls), ok=True),
        )
        return plan

    def _plan_live(
        self, text: str, lowered: str, team_id: str | None = None
    ) -> LlmPlan:
        """Plan one live-app command for a user message (deterministic).

        Maps edit phrasing onto the open app's command surface (never the
        document adapters — the live lane must not touch the imported copy).

        :param text: Stripped user message.
        :param lowered: Lowercased message for pattern matching.
        :param team_id: Owning team id (prefixes the reply when set).
        :returns: :class:`LlmPlan` with ``mock=True`` and one tool call.
        """
        calls: list[ToolCall] = []
        if "rotat" in lowered:
            if "counter" in lowered or "anti" in lowered:
                calls.append(
                    self._call("command_run", {"command": "image.imageRotationccw"})
                )
                reply = "Rotating the open document counterclockwise."
            elif "180" in lowered:
                calls.append(
                    self._call("command_run", {"command": "image.imageRotation"})
                )
                reply = "Rotating the open document 180 degrees."
            else:
                calls.append(
                    self._call("command_run", {"command": "image.imageRotationcw"})
                )
                reply = "Rotating the open document clockwise."
        elif "grayscale" in lowered or "black and white" in lowered:
            calls.append(self._call("command_run", {"command": "image.mode.grayscale"}))
            reply = "Converting the open document to grayscale."
        elif "blur" in lowered:
            calls.append(
                self._call(
                    "command_run",
                    {
                        "command": "filter.blur.gaussianBlur",
                        "params": {"radius": 3},
                    },
                )
            )
            reply = "Blurring the open document."
        elif "save" in lowered:
            calls.append(self._call("doc_save", {}))
            reply = "Saving the open document."
        else:
            summary = (
                "No live edit matched; tell me what to change in the open app document."
            )
            calls.append(self._call("done", {"summary": summary}))
            reply = summary
        if team_id:
            reply = f"[team {team_id}] {reply}"
        plan = LlmPlan(text=reply, tool_calls=calls, mock=True, model="mock")
        log.info(
            "mock plan: %s",
            safe_event(event="mock_plan", count=len(calls), ok=True),
        )
        return plan


__all__ = [
    "AGENT_TOOLS",
    "LIVE_APP_TOOLS",
    "LlmClient",
    "LlmError",
    "LlmPlan",
    "MockBrain",
    "ToolCall",
]
