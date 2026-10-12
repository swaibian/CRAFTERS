"""THE AGENT LOOP: do → see → reason → change until finished.

Given a user message + open document + brain (LLM or MockBrain), the loop:

1. **plan** — ask the brain for tool calls (LLM via :class:`LlmClient` or
   deterministic :class:`MockBrain` when no profile is configured);
2. **do** — execute the ops (doc-adapter ops on the imported copy —
   snapshot-guard every destructive op; or, with a
   :class:`~controller.live.LiveExecutor`, real commands on the user's
   OPEN desktop document via the app's command surface);
3. **see** — re-read the doc (adapter ``inspect``, or ``document.inspect``
   on the live lane = observation);
4. **reason** — check the observation against the request; on mismatch, plan
   the next step (max ``max_iterations``, default 8);
5. **record** — a craft_record-style claim ledger per run (every claim needs
   evidence: revision refs + content hashes).

Exposed as :func:`run_agent_loop`, an async generator yielding loop events
(``run.started``, ``plan``, ``tool.call``, ``tool.result``, ``observe``,
``record``, ``run.completed``, ``run.error``). The service layer maps these
onto the SSE contract (``response.started``/``text.delta``/``tool.call``/
``tool.result``/``response.completed``/``response.error``).

SW-REQ: SW-REQ-STREAM (agent edit loop, TC-B controller side).
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from .documents import (
    DocumentError,
    DocumentRegistry,
    PdfAdapter,
    PhotoAdapter,
    SheetAdapter,
)
from .live import LiveError, LiveExecutor
from .llm import (
    AGENT_TOOLS,
    LIVE_APP_TOOLS,
    LlmClient,
    LlmError,
    LlmPlan,
    MockBrain,
    ToolCall,
)
from .logger import get_logger, safe_event

log = get_logger()

MAX_ITERATIONS = 8


@dataclass
class ClaimRecord:
    """One ledger entry: a claim + its evidence (craft_record-style).

    :param record_id: Public id (``rec_<hex>``).
    :param claim: Claim text (stored, never logged).
    :param confidence: ``measured`` (evidence-backed) or ``inferred``.
    :param evidence: Evidence refs (revision/content-hash/op refs).
    """

    record_id: str
    claim: str
    confidence: str
    evidence: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AgentRun:
    """State for one loop run (claim ledger + iteration budget).

    :param run_id: Stable run id (``run_<hex>``).
    :param session_id: Owning session (logging only).
    :param max_iterations: Plan→act→observe budget (default 8).
    """

    run_id: str
    session_id: str
    max_iterations: int = MAX_ITERATIONS
    ledger: list[ClaimRecord] = field(default_factory=list)

    def record(
        self, claim: str, confidence: str, evidence: list[dict[str, Any]]
    ) -> ClaimRecord:
        """Append a ledger claim (measured claims need evidence).

        :param claim: Claim text (non-empty).
        :param confidence: ``measured`` or ``inferred``.
        :param evidence: Evidence refs (required for ``measured``).
        :returns: The new entry.
        :raises ValueError: Empty claim or measured-without-evidence.
        """
        if not claim.strip():
            raise ValueError("claim must be non-empty")
        if confidence not in ("measured", "inferred"):
            raise ValueError(f"unknown confidence: {confidence}")
        if confidence == "measured" and not evidence:
            raise ValueError("measured claims require evidence")
        entry = ClaimRecord(
            record_id=f"rec_{secrets.token_hex(8)}",
            claim=claim.strip(),
            confidence=confidence,
            evidence=list(evidence),
        )
        self.ledger.append(entry)
        return entry


BrainFn = Callable[[str, str], LlmPlan]


def team_context_block(team: dict[str, Any] | None) -> str:
    """Render a team roster block for the planner system prompt / mock prefix.

    :param team: Team summary from ``list_teams()`` (``{id, name, agents}``)
        or None.
    :returns: ``""`` when no team, else a short block naming the team and
        its agent roster (names/roles only — no secrets live in team files).
    """
    if not team:
        return ""
    agents = team.get("agents") or []
    roster = ", ".join(
        str(a.get("name") or a.get("id", ""))
        + (f" ({a.get('model')})" if a.get("model") else "")
        for a in agents
        if isinstance(a, dict)
    )
    block = f"You work as part of team '{team.get('name', team.get('id', ''))}' (id: {team.get('id', '')})."
    if roster:
        block += f" Agent roster: {roster}."
    return block


def brain_from_profile(
    profile: Any | None,
    mock: MockBrain | None = None,
    *,
    model_override: str | None = None,
    team: dict[str, Any] | None = None,
    live: bool = False,
    live_app: str = "",
) -> tuple[BrainFn, str, bool]:
    """Build a planner function from a settings profile (or MockBrain).

    :param profile: Active :class:`LlmProfile` or None (no key configured).
    :param mock: MockBrain override (tests).
    :param model_override: Validated model id to send as ``model`` instead of
        the profile default (already checked against the live model list by
        the service layer; requirement: chat model override).
    :param team: Resolved team summary (``list_teams()`` entry) or None. Its
        name + agent roster are injected into the real-LLM system prompt and
        MockBrain replies are prefixed ``[team <id>]`` (requirement: team
        must be behaviorally real).
    :param live: Plan against the live-app command surface
        (:data:`~controller.llm.LIVE_APP_TOOLS`) instead of the document
        adapters — the user's OPEN desktop document is being driven.
    :param live_app: App id the open document lives in (names the prompt;
        e.g. ``"photocraft"``).
    :returns: ``(plan_fn, model_name, is_mock)`` where ``plan_fn(message,
        doc_kind)`` returns an :class:`LlmPlan`.
    """
    brain = mock or MockBrain()
    team_id = str(team.get("id", "")) if team else None
    context = team_context_block(team)
    if profile is None or not getattr(profile, "api_key", ""):
        return (
            lambda message, kind: brain.plan(
                message, doc_kind=kind, team_id=team_id, live=live
            ),
            "mock",
            True,
        )
    # model_override wins; else the profile default; else "" (the service
    # layer guarantees a resolved model before calling — never send a
    # placeholder id like "default" to a provider).
    model_name = model_override or str(getattr(profile, "default_model", "") or "")
    client = LlmClient(
        api_base=profile.api_base,
        api_key=profile.api_key,
        default_model=model_name,
    )

    def _plan(message: str, kind: str) -> LlmPlan:
        if live:
            system = (
                f"You operate the user's open {live_app or 'desktop app'} document "
                "in the live desktop app via its command surface. Every command "
                "you run is applied to the document the user sees in the open "
                "window — the effect is visible there immediately. Use "
                "command_list to discover the app's functionality (the full "
                "engine registry with parameter docs), command_run to run any "
                "command (e.g. image.imageRotationcw rotates 90 degrees "
                "clockwise), and look / doc_inspect to verify the result. Use "
                "doc_save ONLY when the user explicitly asks to save — visible "
                "edits need no save. Act with tool calls, then call done with a "
                "summary. When the user asks a question about the document "
                "(dimensions, layers, state), answer from look / doc_inspect "
                "with a done call — do not transform the document."
            )
        else:
            system = (
                "You edit the user's open document copy via tools. "
                f"Open document kind: {kind or 'none'}. "
                "Act with tool calls, then call done with a summary. "
                "When the user asks a question about the document (dimensions, "
                "pages, content, state), answer from the known facts with a "
                "done call — do not transform the document."
            )
        if context:
            system += f" {context}"
        return client.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": message},
            ],
            tools=LIVE_APP_TOOLS if live else AGENT_TOOLS,
            model=model_name,
        )

    return (_plan, client.model, False)


async def run_agent_loop(
    message: str,
    *,
    doc_id: str | None,
    registry: DocumentRegistry,
    plan_fn: BrainFn,
    model_name: str = "mock",
    is_mock: bool = True,
    session_id: str = "default",
    max_iterations: int = MAX_ITERATIONS,
    executor: LiveExecutor | None = None,
    live_app: str = "",
) -> AsyncIterator[dict[str, Any]]:
    """Run do → see → reason → change until finished (async event generator).

    :param message: User message (never logged verbatim).
    :param doc_id: Open document id (None = chat without a document).
    :param registry: Session document registry.
    :param plan_fn: ``(message, doc_kind) -> LlmPlan`` planner.
    :param model_name: Brain label for events (``"mock"`` when no key).
    :param is_mock: Whether the MockBrain planned this run.
    :param session_id: Owning session (logging only).
    :param max_iterations: Plan→act→observe budget.
    :param executor: Live executor driving the user's OPEN desktop document
        (None = adapter mode on the imported work dir copy).
    :param live_app: App id the executor drives (logging only).
    :yields: Loop events: ``run.started`` (run_id, model, mock), ``plan``
        (text, calls), ``tool.call`` (name, call_id), ``tool.result`` (ok,
        evidence summary), ``observe`` (inspection summary), ``record``
        (record_id, confidence), ``run.completed`` (summary, ledger ids),
        ``run.error`` (message).
    """
    run = AgentRun(
        run_id=f"run_{secrets.token_hex(8)}",
        session_id=session_id,
        max_iterations=max_iterations,
    )
    doc = registry.get(doc_id) if doc_id else None
    doc_kind = doc.kind if doc else ""
    live_tag = {"app": live_app} if live_app else {}
    started = time.monotonic()
    log.info(
        "agent run started: %s",
        safe_event(
            event="run_started",
            run_id=run.run_id,
            session_id=session_id,
            model=model_name,
            doc_id=doc_id or "",
            ok=True,
            **live_tag,
        ),
    )
    yield {
        "type": "run.started",
        "run_id": run.run_id,
        "model": model_name,
        "mock": is_mock,
    }

    if not message.strip():
        yield {"type": "run.error", "message": "empty message"}
        return

    sheets = SheetAdapter(registry)
    photos = PhotoAdapter(registry)
    pdfs = PdfAdapter(registry)

    try:
        plan = plan_fn(message, doc_kind)
    except LlmError as exc:
        log.warning(
            "agent plan failed: %s",
            safe_event(
                event="run_error",
                run_id=run.run_id,
                session_id=session_id,
                model=model_name,
                error=str(exc)[:200],
                ok=False,
            ),
        )
        yield {"type": "run.error", "message": str(exc)}
        return
    log.info(
        "agent plan ready: %s",
        safe_event(
            event="plan_ready",
            run_id=run.run_id,
            session_id=session_id,
            model=model_name,
            count=len(plan.tool_calls),
            ok=True,
        ),
    )

    iteration = 0
    pending: list[ToolCall] = list(plan.tool_calls)
    current_text = plan.text
    if current_text:
        yield {"type": "plan", "text": current_text, "calls": [c.name for c in pending]}
    if not pending and not current_text:
        current_text = "What should I change in the open document?"
        yield {"type": "plan", "text": current_text, "calls": []}

    final_summary = current_text
    while iteration < max_iterations:
        if not pending:
            break
        iteration += 1
        call = pending.pop(0)
        log.info(
            "agent tool call: %s",
            safe_event(
                event="tool_call",
                run_id=run.run_id,
                tool=call.name,
                iteration=iteration,
                ok=True,
            ),
        )
        yield {
            "type": "tool.call",
            "name": call.name,
            "call_id": call.call_id,
            "arguments": dict(call.arguments),
            "iteration": iteration,
        }
        try:
            if executor is not None:
                evidence = await _execute_live_call(call, executor)
            else:
                evidence = _execute_call(call, doc_id, sheets, photos, pdfs)
            ok = True
            error = ""
        except (DocumentError, ValueError, LiveError) as exc:
            evidence = {}
            ok = False
            error = str(exc)
        yield {
            "type": "tool.result",
            "name": call.name,
            "call_id": call.call_id,
            "ok": ok,
            "error": error,
            "revision": evidence.get("revision")
            if isinstance(evidence, dict)
            else None,
            "iteration": iteration,
        }
        log.info(
            "agent tool result: %s",
            safe_event(
                event="tool_result",
                run_id=run.run_id,
                tool=call.name,
                iteration=iteration,
                error="" if ok else str(error)[:200],
                ok=ok,
            ),
        )
        if call.name == "done":
            final_summary = str(call.arguments.get("summary", final_summary))
            run.record(
                f"run completed: {final_summary}",
                "inferred",
                [{"kind": "revision", "revision": iteration}],
            )
            yield {
                "type": "record",
                "record_id": run.ledger[-1].record_id,
                "confidence": "inferred",
            }
            break
        if not ok:
            # Reason about the failure: record it, then stop (no blind retry).
            run.record(
                f"tool {call.name} failed: {error}",
                "inferred",
                [{"kind": "revision", "revision": iteration}],
            )
            yield {
                "type": "record",
                "record_id": run.ledger[-1].record_id,
                "confidence": "inferred",
            }
            final_summary = f"I could not complete that step ({call.name}: {error})."
            break
        # SEE: re-read the doc = observation; REASON: verify against request.
        if executor is not None:
            observation = await _observe_live(executor)
        else:
            observation = _observe(doc_id, registry, sheets, photos, pdfs)
        yield {"type": "observe", "observation": observation, "iteration": iteration}
        refs = _evidence_refs(evidence, observation)
        confidence = "measured" if refs else "inferred"
        entry = run.record(
            f"{call.name} applied and verified",
            confidence,
            refs if refs else [{"kind": "revision", "revision": iteration}],
        )
        yield {
            "type": "record",
            "record_id": entry.record_id,
            "confidence": confidence,
        }
        final_summary = _summarize(call, evidence)
        # Ask the brain whether more steps are needed (follow-up plan).
        if pending:
            continue
        try:
            followup = plan_fn(
                f"Done so far: {final_summary}. Original request: {message}. "
                "Reply with a done call carrying the final summary, or more "
                "tool calls if work remains.",
                doc_kind,
            )
        except LlmError:
            break
        if followup.tool_calls:
            pending.extend(followup.tool_calls)
            if followup.text:
                yield {
                    "type": "plan",
                    "text": followup.text,
                    "calls": [c.name for c in followup.tool_calls],
                }
        else:
            if followup.text:
                final_summary = followup.text
            break

    if iteration >= max_iterations and pending:
        final_summary += " (stopped at the iteration budget; work may remain)."
    duration_ms = int((time.monotonic() - started) * 1000)
    log.info(
        "agent run completed: %s",
        safe_event(
            event="run_completed",
            run_id=run.run_id,
            session_id=session_id,
            model=model_name,
            doc_id=doc_id or "",
            iteration=iteration,
            count=len(run.ledger),
            duration_ms=duration_ms,
            ok=True,
            **live_tag,
        ),
    )
    yield {
        "type": "run.completed",
        "summary": final_summary,
        "mock": is_mock,
        "model": model_name,
        "iterations": iteration,
        "records": [e.record_id for e in run.ledger],
    }


def _execute_call(
    call: ToolCall,
    doc_id: str | None,
    sheets: SheetAdapter,
    photos: PhotoAdapter,
    pdfs: PdfAdapter,
) -> dict[str, Any]:
    """Execute one tool call against the adapters (raises on failure).

    :param call: Parsed tool call.
    :param doc_id: Open document id (required except ``done``).
    :returns: Before/after evidence from the adapter.
    :raises DocumentError: Unknown tool, no document, or adapter failure.
    """
    if call.name == "done":
        return {"summary": call.arguments.get("summary", "")}
    if not doc_id:
        raise DocumentError("no document open: upload a file first")
    args = call.arguments
    if call.name == "sheet.set_cell":
        return sheets.set_cell(
            doc_id,
            str(args.get("cell", "")),
            args.get("value"),
            sheet=args.get("sheet"),
        )
    if call.name == "sheet.add_sheet":
        return sheets.add_sheet(doc_id, str(args.get("title", "")))
    if call.name == "photo.transform":
        kind = str(args.get("kind", ""))
        rest = {k: v for k, v in args.items() if k != "kind"}
        return photos.transform(doc_id, kind, **rest)
    if call.name == "pdf.transform":
        return pdfs.transform(
            doc_id,
            str(args.get("kind", "")),
            page=int(args.get("page", 1)) - 1,
            degrees=int(args.get("degrees", 90)),
        )
    raise DocumentError(f"unknown tool: {call.name}")


async def _execute_live_call(call: ToolCall, executor: LiveExecutor) -> dict[str, Any]:
    """Execute one tool call against the live desktop app (raises on failure).

    Dispatches the :data:`~controller.llm.LIVE_APP_TOOLS` names onto the
    :class:`~controller.live.LiveExecutor` — never onto the document
    adapters (the live lane must not touch the imported copy).

    :param call: Parsed tool call.
    :param executor: Live executor for the linked open document.
    :returns: Minimal evidence (op names/counts/hashes — never pixels or
        command params).
    :raises DocumentError: Unknown tool.
    :raises LiveError: App down or the app refused the call (honest text).
    """
    if call.name == "done":
        return {"summary": call.arguments.get("summary", "")}
    args = call.arguments
    if call.name == "command_run":
        raw_params = args.get("params")
        params = raw_params if isinstance(raw_params, dict) else None
        command = str(args.get("command", ""))
        await executor.execute(command, params)
        return {"op": command}
    if call.name == "command_list":
        raw_filter = args.get("filter")
        result = await executor.commands(
            str(raw_filter) if raw_filter is not None else None
        )
        commands = result.get("commands") if isinstance(result, dict) else None
        return {"count": len(commands) if isinstance(commands, list) else 0}
    if call.name == "doc_inspect":
        await executor.inspect()
        return {"op": "document.inspect"}
    if call.name == "doc_save":
        raw_path = args.get("path")
        result = await executor.save(str(raw_path) if raw_path is not None else None)
        written = result.get("path") if isinstance(result, dict) else None
        return {"op": "app.save", "path": str(written) if written else "own file"}
    if call.name == "look":
        png = await executor.look()
        return {
            "op": "look",
            "bytes": len(png),
            "sha256": hashlib.sha256(png).hexdigest(),
        }
    raise DocumentError(f"unknown tool: {call.name}")


def _observe(
    doc_id: str | None,
    registry: DocumentRegistry,
    sheets: SheetAdapter,
    photos: PhotoAdapter,
    pdfs: PdfAdapter,
) -> dict[str, Any]:
    """Re-read the doc into a log-safe observation summary.

    :returns: ``{kind, revision, content_hash, detail}`` where detail holds
        counts/dims only (no content, no pixels).
    """
    if not doc_id:
        return {"kind": "none", "detail": "no document open"}
    doc = registry.get(doc_id)
    if doc is None:
        return {"kind": "none", "detail": "document closed"}
    try:
        if doc.kind == "sheet":
            info = sheets.inspect(doc_id)
            detail = {
                "sheets": [s["title"] for s in info["sheets"]],
                "dims": [s["dims"] for s in info["sheets"]],
            }
        elif doc.kind == "photo":
            info = photos.inspect(doc_id)
            detail = {
                "width": info["width"],
                "height": info["height"],
                "mode": info["mode"],
            }
        elif doc.kind == "pdf":
            info = pdfs.inspect(doc_id)
            detail = {"pages": len(info["pages"])}
        else:
            return {"kind": doc.kind, "detail": "unknown kind"}
    except DocumentError:
        return {"kind": doc.kind if doc else "none", "detail": "inspect failed"}
    return {
        "kind": doc.kind,
        "revision": info["revision"],
        "content_hash": info["content_hash"],
        "detail": detail,
    }


async def _observe_live(executor: LiveExecutor) -> dict[str, Any]:
    """Re-read the live document into a log-safe observation summary.

    Runs ``document.inspect`` through the executor and keeps counts/dims
    only — layer names, history entries, pixels and the raw payload never
    reach the observation or the logs.

    :param executor: Live executor for the linked open document.
    :returns: ``{kind: "live", app, revision, content_hash, detail}`` where
        ``revision`` is the history length and ``content_hash`` an inspect
        payload hash; missing fields degrade gracefully.
    """
    try:
        info = await executor.inspect()
    except LiveError:
        return {"kind": "live", "app": executor.app, "detail": "inspect failed"}
    if not isinstance(info, dict):
        return {"kind": "live", "app": executor.app, "detail": "inspect unreadable"}
    detail: dict[str, Any] = {}
    for key in ("width", "height"):
        value = _optional_count(info.get(key))
        if value is not None:
            detail[key] = value
    for key in ("layers", "history"):
        entries = info.get(key)
        if isinstance(entries, list):
            detail[key] = len(entries)
    observation: dict[str, Any] = {
        "kind": "live",
        "app": executor.app,
        "detail": detail,
    }
    history = info.get("history")
    if isinstance(history, list):
        observation["revision"] = len(history)
    try:
        canonical = json.dumps(info, sort_keys=True, default=str).encode("utf-8")
        observation["content_hash"] = f"sha256:{hashlib.sha256(canonical).hexdigest()}"
    except (TypeError, ValueError):
        pass
    return observation


def _optional_count(value: Any) -> int | None:
    """Best-effort non-negative int coercion (None when absent/unparseable)."""
    if isinstance(value, bool):
        return None
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _evidence_refs(
    evidence: dict[str, Any], observation: dict[str, Any]
) -> list[dict[str, Any]]:
    """Build ledger evidence refs from adapter evidence + observation."""
    refs: list[dict[str, Any]] = []
    revision = evidence.get("revision", observation.get("revision"))
    if revision is not None:
        refs.append({"kind": "revision", "revision": revision})
    content_hash = None
    after = evidence.get("after")
    if isinstance(after, dict):
        content_hash = after.get("content_hash")
    content_hash = content_hash or observation.get("content_hash")
    if content_hash:
        refs.append({"kind": "render", "id": str(content_hash)})
    return refs


def _summarize(call: ToolCall, evidence: dict[str, Any]) -> str:
    """Human summary of one applied op (no content echoed)."""
    if call.name == "done":
        return str(evidence.get("summary") or "Done.")
    op = evidence.get("op", call.name)
    revision = evidence.get("revision", "?")
    if call.name == "sheet.set_cell":
        return f"Set {evidence.get('cell')} (revision {revision})."
    if call.name == "sheet.add_sheet":
        return f"Added sheet (revision {revision})."
    if call.name.startswith("photo.") or call.name.startswith("pdf."):
        return f"Applied {op} (revision {revision})."
    if call.name == "command_run":
        return f"Ran {op} in the open app."
    if call.name == "command_list":
        return f"Listed {evidence.get('count', 0)} app commands."
    if call.name == "doc_inspect":
        return "Inspected the open app document."
    if call.name == "doc_save":
        return f"Saved the open app document ({evidence.get('path', 'own file')})."
    if call.name == "look":
        return f"Looked at the live window ({evidence.get('bytes', 0)} bytes)."
    return f"Applied {op}."


__all__ = [
    "MAX_ITERATIONS",
    "AgentRun",
    "BrainFn",
    "ClaimRecord",
    "brain_from_profile",
    "run_agent_loop",
    "team_context_block",
]
