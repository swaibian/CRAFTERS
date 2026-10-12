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
   the next step (max ``max_iterations``, default 32);
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

import asyncio
import base64
import hashlib
import json
import re
import secrets
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from .app_skills import app_skill
from .commands import CommandCatalog
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

MAX_ITERATIONS = 32

#: Tools whose effect applies to the document — an identical repeat would
#: apply it twice (rotating again, writing the cell again).
MUTATING_TOOLS = frozenset(
    {
        "command_run",
        "doc_save",
        "photo.transform",
        "pdf.transform",
        "sheet.set_cell",
        "sheet.add_sheet",
    }
)

#: Mutating tools whose identical repeat is refused anywhere in one run
#: (non-idempotent: rotation/filter commands, page ops). ``doc_save`` is
#: excluded — re-saving the same file is harmless.
RUN_GUARD_TOOLS = MUTATING_TOOLS - {"doc_save"}

#: A bare registry-style command id (``image.imageRotation.90cw``); anything
#: else in ``command_run`` is a double-wrapped envelope, not an id.
_COMMAND_ID_RE = re.compile(r"^[A-Za-z_][\w.]*$")


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
    :param max_iterations: Plan→act→observe budget (default 32).
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
    history: list[dict[str, Any]] | None = None,
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

    messages: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []

    def _plan(message: str, kind: str) -> LlmPlan:
        if live:
            system = (
                f"You operate the user's open {live_app or 'desktop app'} document "
                "in the live desktop app via its command surface. Every command "
                "you run is applied to the document the user sees in the open "
                "window — the effect is visible there immediately. Follow this "
                "workflow on every request: 1) understand what the user wants "
                "changed; 2) use the loaded app skill for known operations; "
                "for unfamiliar operations call command_list with short keywords (e.g. 'blend', "
                "'duplicate', 'opacity', 'filter') to discover the exact command "
                "ids and their params — the registry contains everything the app "
                "can do: layers (duplicate, move, merge), blend modes (Multiply, "
                "Screen, … as PARAM VALUES of one layer command, never separate "
                "ids), opacity, transforms, filters, adjustments, text, "
                "selection; 3) call command_run with the exact id you found (ids "
                "look like image.imageRotation.90cw) — never invent ids; "
                "4) verify with look / doc_inspect; 5) call doc_save ONLY when "
                "the user explicitly asks to save — visible edits need no save; "
                "6) finish with done carrying a summary of what changed. When "
                "the user asks a question about the document (dimensions, layers, "
                "state), answer from look / doc_inspect with a done call — do "
                "not transform the document."
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
        if not messages:
            skill = app_skill(live_app) if live else ""
            messages.append({"role": "system", "content": system + "\n" + skill})
            for entry in (history or [])[-12:]:
                if entry.get("role") in {"user", "assistant"}:
                    messages.append({"role": entry["role"], "content": entry.get("text", "")})
        messages.extend(images)
        images.clear()
        messages.append({"role": "user", "content": message})
        plan = client.chat(
            list(messages),
            tools=LIVE_APP_TOOLS if live else AGENT_TOOLS,
            model=model_name,
        )
        assistant: dict[str, Any] = {"role": "assistant", "content": plan.text or None}
        if plan.tool_calls:
            assistant["tool_calls"] = [
                {"id": c.call_id, "type": "function", "function": {
                    "name": c.name, "arguments": json.dumps(c.arguments)}}
                for c in plan.tool_calls
            ]
        messages.append(assistant)
        return plan

    def _result(call: ToolCall, evidence: dict[str, Any], ok: bool, error: str) -> None:
        data = {k: v for k, v in evidence.items() if k != "image_url"}
        messages.append({"role": "tool", "tool_call_id": call.call_id,
                         "content": json.dumps({"ok": ok, "error": error, "result": data}, default=str)})
        if evidence.get("image_url"):
            images.append({"role": "user", "content": [
                {"type": "text", "text": "Live app window screenshot. Locate the canvas; coordinates for edits must be document pixels, not window pixels. If mapping is ambiguous, request clarification."},
                {"type": "image_url", "image_url": {"url": evidence["image_url"]}},
            ]})

    _plan.tool_result = _result  # type: ignore[attr-defined]

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
    catalog: CommandCatalog | None = None,
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
    :param catalog: Command registry the app exposes (live lane) — used to
        suggest nearest ids when the app rejects a command (None = no
        suggestions).
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
        initial = await _observe_live(executor) if executor is not None and not is_mock else None
        request = message
        if initial is not None and not is_mock:
            request += "\nInitial live document state: " + json.dumps(initial)
        plan = await asyncio.to_thread(plan_fn, request, doc_kind)
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
    last_call_key: tuple[str, str] = ("", "")
    same_call_streak = 0
    step_summaries: list[str] = []
    prev_observation: dict[str, Any] | None = initial
    mutation_effects: dict[tuple[str, str], bool] = {}
    last_look_hash: str | None = None
    discovery_keys: set[tuple[str, str]] = set()
    stalled_reads = 0
    outcome = "succeeded"
    correction_attempts = 0
    while iteration < max_iterations:
        if not pending:
            break
        iteration += 1
        call = pending.pop(0)
        call_key = (
            call.name,
            json.dumps(call.arguments, sort_keys=True, default=str),
        )
        same_call_streak = same_call_streak + 1 if call_key == last_call_key else 1
        log.info(
            "agent tool call: %s",
            safe_event(
                event="tool_call",
                run_id=run.run_id,
                tool=call.name,
                iteration=iteration,
                call_id=call.call_id,
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
        repeat = call_key == last_call_key and call.name != "done"
        repeated_edit = repeat and call.name in MUTATING_TOOLS
        already_applied = call.name in RUN_GUARD_TOOLS and call_key in mutation_effects
        # Read-only calls (command_list/doc_inspect/look) are never refused —
        # repeating them wastes budget but must not kill the run the way the
        # old 3-strikes rule did ("I could not complete that step" on a
        # discovery call). Only mutations are double-applied hazards.
        repeated_too_much = (
            repeat and same_call_streak > 2 and call.name in MUTATING_TOOLS
        )
        if repeated_edit or repeated_too_much or already_applied:
            # Identical mutating call twice would apply the change twice
            # (e.g. rotating again); any call three times in a row is a
            # planning loop (e.g. re-listing commands). Stop honestly
            # instead of corrupting the document or burning the budget.
            evidence = {}
            ok = False
            if already_applied:
                error = (
                    f"{call.name} with these exact arguments was already "
                    "applied earlier in this run — running it again would "
                    "apply the change twice (e.g. rotate again); call done "
                    "if the request is satisfied, or use different arguments"
                )
            else:
                error = (
                    f"{call.name} was already run with these arguments — "
                    "repeating it would change nothing new (or apply the edit "
                    "twice); call done or pick a different command"
                )
        else:
            if call.name in RUN_GUARD_TOOLS and prev_observation is None:
                # Baseline before the first edit so the after-state diff is
                # a real "did my edit land?" verdict, not a blind first look.
                if executor is not None:
                    prev_observation = await _observe_live(executor)
                else:
                    prev_observation = _observe(doc_id, registry, sheets, photos, pdfs)
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
                if (
                    catalog is not None
                    and call.name == "command_run"
                    and "unknown command" in error.lower()
                ):
                    hints = catalog.suggest(_attempted_command_id(call.arguments))
                    if hints:
                        error += (
                            " — did you mean: "
                            + ", ".join(hints)
                            + "? Use command_list to discover ids."
                        )
        last_call_key = call_key
        if ok and call.name in RUN_GUARD_TOOLS:
            mutation_effects[call_key] = True
        if ok and call.name == "look" and isinstance(evidence, dict):
            shot_hash = evidence.get("sha256")
            if isinstance(shot_hash, str):
                evidence["changed"] = (
                    None if last_look_hash is None else shot_hash != last_look_hash
                )
                last_look_hash = shot_hash
        receive_result = getattr(plan_fn, "tool_result", None)
        if receive_result is not None:
            receive_result(call, evidence, ok, error)
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
            outcome = "failed"
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
            if receive_result is not None and not (already_applied or repeated_edit) and correction_attempts < 2:
                correction_attempts += 1
                try:
                    correction = await asyncio.to_thread(
                        plan_fn,
                        f"The last tool failed: {error}. Original request: {message}. "
                        "Use the retained tool result and app guide to correct the arguments or inspect the exact contract. "
                        "Do not repeat identical failed arguments. If blocked, call done with an honest explanation.",
                        doc_kind,
                    )
                except LlmError as exc:
                    final_summary = f"Unable to recover from the tool failure: {exc}."
                    break
                if correction.tool_calls:
                    pending = list(correction.tool_calls)
                    outcome = "succeeded"
                    if correction.text:
                        yield {"type": "plan", "text": correction.text, "calls": [c.name for c in pending]}
                    continue
            if already_applied or repeated_edit:
                final_summary = (
                    f"Stopped: {call.name} would have applied the same edit "
                    "a second time — the earlier application stands."
                )
            elif repeated_too_much:
                final_summary = (
                    f"Stopped: {call.name} was repeated without progress — "
                    "nothing new to report."
                )
            else:
                final_summary = (
                    f"I could not complete that step ({call.name}: {error})."
                )
            break
        # SEE: re-read the doc = observation; REASON: verify against request.
        if executor is not None:
            observation = await _observe_live(executor)
        else:
            observation = _observe(doc_id, registry, sheets, photos, pdfs)
        changed = _state_changed(prev_observation, observation)
        previous_hint = _revision_hint(prev_observation)
        yield {
            "type": "observe",
            "observation": observation,
            "changed": changed,
            "iteration": iteration,
        }
        refs = _evidence_refs(evidence, observation)
        confidence = "measured" if refs else "inferred"
        if call.name in MUTATING_TOOLS:
            claim = (
                f"{call.name} applied and verified"
                if changed is not False
                else f"{call.name} ran but the document state did not change"
            )
        else:
            claim = f"{call.name} completed"
        entry = run.record(
            claim,
            confidence,
            refs if refs else [{"kind": "revision", "revision": iteration}],
        )
        yield {
            "type": "record",
            "record_id": entry.record_id,
            "confidence": confidence,
        }
        final_summary = _summarize(call, evidence)
        step_summaries.append(final_summary)
        prev_observation = observation
        if call.name in {"command_list", "command_describe", "doc_inspect", "look"}:
            stalled_reads = stalled_reads + 1 if call_key in discovery_keys else 0
            discovery_keys.add(call_key)
            if stalled_reads >= 4:
                outcome = "blocked"
                final_summary = "Stopped because repeated discovery produced no actionable progress. No further edit was applied; the target or command contract needs clarification."
                break
        else:
            stalled_reads = 0
            discovery_keys.clear()
        # Ask the brain whether more steps are needed (follow-up plan).
        if pending:
            continue
        steps_line = " ".join(f"{i + 1}) {s}" for i, s in enumerate(step_summaries))
        try:
            followup = await asyncio.to_thread(plan_fn,
                f"Done so far: {steps_line} {_evidence_hint(evidence)} "
                f"Original request: {message}. "
                f"Current document state: "
                f"{_state_line(observation, changed, previous=previous_hint, mutated=call.name in MUTATING_TOOLS)}. "
                f"Structured observation: {json.dumps(observation, default=str)}. "
                "If the state already satisfies the request, reply with a "
                "done call carrying the final summary — never repeat an edit "
                "that already landed. Otherwise reply with the next tool "
                "calls (use the app skill or retained contracts; discover unfamiliar ids with command_list).",
                doc_kind,
            )
        except LlmError as exc:
            outcome = "failed"
            final_summary = f"Unable to continue: {exc}. Completed operations: " + " ".join(step_summaries)
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
        outcome = "budget_exhausted"
        recap = " ".join(step_summaries) if step_summaries else final_summary
        final_summary = (
            f"{recap} (stopped at the iteration budget after {iteration} "
            "steps; work may remain)."
        )
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
            outcome=outcome,
            ok=outcome == "succeeded",
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
        "outcome": outcome,
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


def _unwrap_command_value(value: Any) -> Any:
    """Peel one double-wrapped ``command_run`` envelope layer.

    LLMs occasionally wrap the call (upstream MCP spells the arg ``id``, or
    the whole ``{"command": ..., "params": ...}`` envelope lands in the
    ``command`` value — even as a JSON string). One step unwraps dicts
    carrying ``command``/``id`` and JSON-object strings of the same shape.

    :param value: Current candidate value.
    :returns: The inner candidate, or ``value`` when no envelope is present.
    """
    if isinstance(value, dict):
        inner = value.get("command")
        if inner is None:
            inner = value.get("id")
        return value if inner is None else inner
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                parsed = json.loads(stripped)
            except ValueError:
                return value
            if isinstance(parsed, dict):
                return parsed
    return value


def _normalize_command_run_args(
    arguments: dict[str, Any],
) -> tuple[str, dict[str, Any] | None]:
    """Unwrap one ``command_run`` argument mapping into ``(command_id, params)``.

    Accepts ``command`` or ``id``; the value may itself be a
    ``{"command": ..., "params": ...}`` / ``{"id": ...}`` envelope or a JSON
    string of one (unwrapped iteratively). Params follow the innermost
    envelope that carries them, else the top-level ``params`` object.

    :param arguments: Raw tool-call arguments.
    :returns: ``(bare command id, params dict or None)``.
    :raises DocumentError: No recognizable id, or the id is not bare
        registry style (``^[A-Za-z_][\\w.]*$``).
    """
    original: Any = arguments.get("command")
    if original is None:
        original = arguments.get("id")
    raw: Any = original
    params: Any = arguments.get("params")
    for _ in range(4):
        if isinstance(raw, dict):
            nested = raw.get("params")
            if isinstance(nested, dict):
                params = nested
        unwrapped = _unwrap_command_value(raw)
        if unwrapped is raw:
            if isinstance(raw, dict):
                raw = None
            break
        raw = unwrapped
    command = raw.strip() if isinstance(raw, str) else ""
    if not _COMMAND_ID_RE.match(command):
        got = command if command else str(original)[:60]
        raise DocumentError(
            "command_run needs a bare command id (e.g. image.imageRotation.90cw) "
            "— list ids with command_list; got: " + got[:60]
        )
    return command, params if isinstance(params, dict) else None


def _attempted_command_id(arguments: dict[str, Any]) -> str:
    """Best-effort id the planner sent (for suggestion hints; never raises)."""
    try:
        command, _params = _normalize_command_run_args(arguments)
        return command
    except DocumentError:
        raw = arguments.get("command", arguments.get("id"))
        return str(raw)[:60] if raw is not None else ""


async def _execute_live_call(call: ToolCall, executor: LiveExecutor) -> dict[str, Any]:
    """Execute one tool call against the live desktop app (raises on failure).

    Dispatches the :data:`~controller.llm.LIVE_APP_TOOLS` names onto the
    :class:`~controller.live.LiveExecutor` — never onto the document
    adapters (the live lane must not touch the imported copy).
    ``command_run`` arguments are normalized first (``command`` or ``id``,
    nested/stringified envelopes unwrapped) so a double-wrapped call fails
    with one clear hint instead of an app-side "unknown command" wall.
    ``command_list`` filters client-side (the desktop ``engine.commands``
    ignores its ``filter`` param and always answers the whole registry) —
    ranked through :class:`~controller.commands.CommandCatalog` built
    from the fetched entries, with the params schema kept for the planner.

    :param call: Parsed tool call.
    :param executor: Live executor for the linked open document.
    :returns: Minimal evidence (op names/counts/hashes — never pixels or
        file content).
    :raises DocumentError: Unknown tool or non-bare command id.
    :raises LiveError: App down or the app refused the call (honest text).
    """
    if call.name == "done":
        return {"summary": call.arguments.get("summary", "")}
    args = call.arguments
    if call.name == "command_run":
        command, params = _normalize_command_run_args(args)
        result = await executor.execute(command, params or {})
        return {"op": command, "result": result}
    if call.name == "command_describe":
        command = str(args.get("command", ""))
        result = await executor.commands()
        entries = result.get("commands", [])
        entry = next((e for e in entries if e.get("id") == command), None)
        if entry is None:
            raise DocumentError(f"unknown command: {command}")
        return {"entries": [entry], "count": 1, "total": len(entries)}
    if call.name == "command_list":
        raw_filter = args.get("filter")
        filter_text = str(raw_filter).strip() if raw_filter is not None else ""
        result = await executor.commands(filter_text or None)
        commands = result.get("commands") if isinstance(result, dict) else None
        entries = (
            [e for e in commands if isinstance(e, dict) and e.get("id")]
            if isinstance(commands, list)
            else []
        )
        total = len(entries)
        if filter_text:
            # Filter client-side: the desktop ignores `filter`, and the
            # registry's own substring semantics cannot match "rotate" to
            # "image.imageRotation…" — the catalog's ranked search can.
            # Always index the FETCHED entries (they are the app's true
            # registry; a catalog fetched earlier may be stale or from a
            # different fixture).
            ranked = CommandCatalog(entries).search(filter_text, limit=50)
            by_id = {e["id"]: e for e in entries}
            matched = [by_id[e["id"]] for e in ranked]
        else:
            matched = entries
        listed: list[dict[str, Any]] = []
        for entry in matched:
            # Params schema rides along: the planner must learn HOW to call
            # an id (e.g. curves takes {"points": [[in,out],…]}) — a bare
            # id+label listing cannot support "reduce the highlights".
            raw_params = entry.get("params")
            params_doc = str(raw_params) if raw_params is not None else ""
            listed.append(
                {
                    "id": str(entry.get("id", "")),
                    "label": str(entry.get("label") or entry.get("name") or ""),
                    "params": params_doc,
                    "enabled": entry.get("enabled"),
                    "menu": entry.get("menu", []),
                }
            )
        evidence: dict[str, Any] = {
            "count": len(matched),
            "total": total,
            "filter": filter_text,
            "ids": [e["id"] for e in listed],
            "entries": listed,
        }
        return evidence
    if call.name == "doc_inspect":
        info = await executor.inspect()
        detail = _live_detail(info) if isinstance(info, dict) else {}
        return {"op": "document.inspect", "detail": detail}
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
            "image_url": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
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


def _live_detail(info: dict[str, Any]) -> dict[str, Any]:
    """Compact document summary from a ``document.inspect`` payload.

    Keeps counts/dims plus a one-line-per-layer stack summary (name, kind,
    blend, opacity) so the planner can verify layer-level requests
    (duplicate, blend mode, reorder). Never includes pixels or layer
    content.

    :param info: Raw ``document.inspect`` payload.
    :returns: ``{width, height, layers, history, layer_summary}`` — only
        the keys that parsed.
    """
    detail: dict[str, Any] = {}
    for key in ("activeLayer", "selectedLayers", "hasSelection", "selectionBounds", "revision", "mode", "depth"):
        if key in info:
            detail[key] = info[key]
    for key in ("width", "height"):
        value = _optional_count(info.get(key))
        if value is not None:
            detail[key] = value
    layers = info.get("layers")
    if isinstance(layers, list):
        detail["layers"] = len(layers)
        detail["layer_tree"] = [
            _planner_layer(node) for node in layers if isinstance(node, dict)
        ]
        stack = _layer_summary(layers)
        if stack:
            detail["layer_summary"] = stack
    history = info.get("history")
    if isinstance(history, list):
        detail["history"] = len(history)
    return detail


def _planner_layer(node: dict[str, Any]) -> dict[str, Any]:
    """Retain targeting and edit properties without unrelated document text."""
    keys = ("id", "name", "kind", "blend", "opacity", "fill", "visible", "bounds",
            "selected", "hasMask", "clipped", "adjustment")
    result = {key: node[key] for key in keys if key in node}
    if isinstance(node.get("children"), list):
        result["children"] = [_planner_layer(child) for child in node["children"] if isinstance(child, dict)]
    return result


def _layer_summary(layers: list[Any], limit: int = 12) -> list[str]:
    """Flatten a layer tree into short ``name (kind, blend, opacity%)`` lines.

    :param layers: Layer node list from ``document.inspect`` (may nest
        ``children``).
    :param limit: Maximum lines (guard against huge documents).
    :returns: One line per layer, outermost first.
    """
    lines: list[str] = []

    def _walk(nodes: list[Any]) -> None:
        for node in nodes:
            if len(lines) >= limit:
                return
            if not isinstance(node, dict):
                continue
            name = str(node.get("name") or node.get("kind") or "?")[:40]
            kind = str(node.get("kind") or "")
            blend = str(node.get("blend") or "")
            opacity = node.get("opacity")
            pieces = [p for p in (kind, blend) if p]
            if isinstance(opacity, (int, float)) and not isinstance(opacity, bool):
                pieces.append(f"{opacity * 100:g}%")
            suffix = f" ({', '.join(pieces)})" if pieces else ""
            lines.append(f"{name}{suffix}")
            children = node.get("children")
            if isinstance(children, list):
                _walk(children)

    _walk(layers)
    return lines


async def _observe_live(executor: LiveExecutor) -> dict[str, Any]:
    """Re-read the live document into a log-safe observation summary.

    Runs ``document.inspect`` through the executor and keeps counts/dims
    plus layer names/blends (needed to verify layer-level edits) — pixels
    and layer content never reach the observation or the logs.

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
    detail = _live_detail(info)
    observation: dict[str, Any] = {
        "kind": "live",
        "app": executor.app,
        "detail": detail,
    }
    history = info.get("history")
    if "revision" in info:
        observation["revision"] = info["revision"]
    elif isinstance(history, list):
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


def _state_changed(
    before: dict[str, Any] | None, after: dict[str, Any] | None
) -> bool | None:
    """Whether the document state moved between two observations.

    Compares the inspect hash (includes history) then the summary
    fields — the planner's proof that an edit actually landed.

    :param before: Previous observation (None on the first step).
    :param after: Current observation.
    :returns: True/False when both sides are known, else None.
    """
    if not before or not after:
        return None
    old_hash, new_hash = before.get("content_hash"), after.get("content_hash")
    if old_hash and new_hash:
        return old_hash != new_hash
    return before.get("detail") != after.get("detail") or (
        before.get("revision") != after.get("revision")
    )


def _state_line(
    observation: dict[str, Any],
    changed: bool | None,
    *,
    previous: str = "",
    mutated: bool = True,
) -> str:
    """One-line document state (plus change verdict) for the planner.

    :param observation: Latest observation dict.
    :param changed: Verdict from :func:`_state_changed`.
    :param previous: Short label of the earlier state (e.g. ``"history 2"``).
    :param mutated: Whether the last step was an edit (read-only steps
        must not be blamed for "no visible effect").
    :returns: e.g. ``48x32 px, 2 layers, history 3 (changed since the
        previous step — the edit landed)``.
    """
    detail = observation.get("detail")
    detail = detail if isinstance(detail, dict) else {}
    bits = []
    if "width" in detail and "height" in detail:
        bits.append(f"{detail['width']}x{detail['height']} px")
    if "layers" in detail:
        bits.append(f"{detail['layers']} layers")
    names = detail.get("layer_summary")
    if isinstance(names, list) and names:
        bits.append("layer stack: " + "; ".join(str(n) for n in names[:12]))
    revision = observation.get("revision")
    if revision is not None:
        bits.append(f"history {revision}")
    state = ", ".join(bits) or "unknown"
    if changed is True:
        verdict = "changed since the previous step — the edit landed"
        if previous:
            verdict += f" (was {previous})"
    elif changed is False:
        if mutated:
            verdict = (
                "UNCHANGED since the previous step — the edit did NOT land; "
                "verify the command id/params before retrying"
            )
        else:
            verdict = "unchanged since the previous step (read-only step)"
    else:
        verdict = "first state reading of this run"
    return f"{state} ({verdict})"


def _revision_hint(observation: dict[str, Any] | None) -> str:
    """Short label of an observation's revision (for change verdicts)."""
    if not observation:
        return ""
    revision = observation.get("revision")
    return f"history {revision}" if revision is not None else ""


def _entry_line(entry: dict[str, Any]) -> str:
    """One registry entry as ``id (label; params schema)`` for prompts."""
    command_id = str(entry.get("id") or "?")
    label = str(entry.get("label") or "")
    params = str(entry.get("params") or "").strip()
    bits = [b for b in (label, params) if b]
    return f"{command_id} ({'; '.join(bits)})" if bits else command_id


def _evidence_hint(evidence: dict[str, Any]) -> str:
    """Compact tool-result hint for the follow-up planner prompt.

    Surfaces what the tool actually returned (``command_list`` hits as
    ``id (label; params schema)`` entries capped at 12 so the planner can
    pick the right registry id AND form its arguments (e.g. curves needs
    ``{"points": [[in,out],…]}``), saved path from ``doc_save``, …) instead
    of blindly repeating the call. Params SCHEMAS are included; pixels and
    file content never are.

    :param evidence: Evidence dict from the executed call.
    :returns: One short sentence (``""`` when there is nothing to add).
    """
    entries = evidence.get("entries")
    if isinstance(entries, list) and entries:
        shown = ", ".join(_entry_line(e) for e in entries[:12] if isinstance(e, dict))
        more = "" if len(entries) <= 12 else f", … ({len(entries) - 12} more)"
        count = evidence.get("count", len(entries))
        total = evidence.get("total", count)
        filter_text = str(evidence.get("filter") or "")
        scope = f"matching '{filter_text}'" if filter_text else "in the registry"
        return (
            f"Commands {scope} ({count} of {total}): {shown}{more}. "
            "Run one with command_run, passing params per its schema (omit "
            "params when the schema is empty), or refine the filter."
        )
    if evidence.get("entries") == [] and evidence.get("filter"):
        return (
            f"No commands match filter '{evidence['filter']}' — try a "
            "different keyword or command_list without a filter."
        )
    ids = evidence.get("ids")
    if isinstance(ids, list) and ids:
        shown = ", ".join(str(i) for i in ids[:40])
        more = "" if len(ids) <= 40 else f", … ({len(ids) - 40} more)"
        return f"Available commands include: {shown}{more}."
    path = evidence.get("path")
    if path:
        return f"Saved to: {path}."
    detail = evidence.get("detail")
    if isinstance(detail, dict) and detail:
        bits = []
        if "width" in detail and "height" in detail:
            bits.append(f"{detail['width']}x{detail['height']} px")
        if "layers" in detail:
            bits.append(f"{detail['layers']} layers")
        names = detail.get("layer_summary")
        if isinstance(names, list) and names:
            bits.append("stack: " + "; ".join(str(n) for n in names[:12]))
        if bits:
            return "Document reads: " + ", ".join(bits) + "."
    if evidence.get("changed") is True:
        return "Window pixels changed since the previous look."
    if evidence.get("changed") is False:
        return (
            "Window pixels are UNCHANGED since the previous look — the "
            "edit may not be visible (or the window is stale)."
        )
    return ""


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
        count = evidence.get("count", 0)
        total = evidence.get("total", count)
        filter_text = str(evidence.get("filter") or "")
        if filter_text:
            return f"Listed {count} of {total} commands matching '{filter_text}'."
        return f"Listed {count} app commands."
    if call.name == "doc_inspect":
        return "Inspected the open app document."
    if call.name == "doc_save":
        return f"Saved the open app document ({evidence.get('path', 'own file')})."
    if call.name == "look":
        if evidence.get("changed") is True:
            return f"Looked at the live window ({evidence.get('bytes', 0)} bytes; pixels changed)."
        if evidence.get("changed") is False:
            return (
                f"Looked at the live window ({evidence.get('bytes', 0)} bytes; "
                "pixels UNCHANGED since the previous look)."
            )
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
