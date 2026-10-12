# Live-agent failure diagnosis and enhancement plan

## Findings

Checked the running controller's `/api/conversations`, `/api/chat/history`, and
`/api/live/documents`, the `.local-run` logs, controller/view implementation,
the captured 818-command registry, and PhotoCraft's upstream inspection source.
The conversation used `meta/muse-spark-1.3-contributor`.

The desktop execution bridge is connected. Duplication succeeded and the app
still reports an active 1024×1024 dirty document. The main failures are in the
controller's delivery of capabilities, state, and perception to the model.

### What the available records prove

| Request | Evidence | Conclusion |
|---|---|---|
| Duplicate background | Stored assistant response reports two layers and successful duplication; supplied UI transcript shows three tool calls. | A simple selected-layer operation successfully traversed the bridge. |
| Make duplicate B&W | User request is stored, but no corresponding assistant completion is stored. Supplied transcript repeatedly shows history 2. | It did not demonstrate a completed edit. Exact calls and termination cause are not retained. |
| Set duplicate to Screen | User request is stored, but no corresponding assistant completion is stored. Supplied transcript repeatedly shows history 2. | It did not demonstrate a completed edit. Exact calls and termination cause are not retained. |
| Circle background people | Stored final recap contains 12 `look`, eight `doc_inspect`, and 12 `command_list` calls, then budget exhaustion. No `command_run` appears. | This run spent all 32 tool iterations observing/searching and never attempted the edit. |

`.local-run/controller.log` contains HTTP access/startup records, not the
controller's `agent`/`llm` INFO events. `gateway.log` and `view.log` show startup
only. One earlier document-list request returned 502 before a later successful
launch/attach. That earlier error does not explain the later discovery loop.
Chat in the live lane calls the desktop through `LiveExecutor` directly, so
gateway startup logs cannot reconstruct these tool executions.

## Root causes and supporting code

1. **Every LLM step restarts the conversation.**
   `controller/agent.py:251–258` sends only a system message and one user
   message. Follow-up planning at `:578–589` substitutes a prose recap, with
   detailed evidence from only the last tool. There are no assistant
   tool-call messages or correlated `role: tool` results. An intervening
   inspection loses previously discovered command schemas; the recap remembers
   only that commands were listed.

2. **Cross-request context is stored but never passed to the planner.**
   `controller/service.py:1105–1115,1152–1163` passes the current request alone.
   The model cannot reliably ground “the duplicated layer” or “the new layer”
   in earlier edits. The initial plan also receives no initial live state.

3. **`look` does not let the model see.**
   `controller/agent.py:842–848` reduces the PNG to byte count and SHA-256.
   No image content is sent in `brain_from_profile` or its follow-ups. The tool
   description promises visual perception, but only pixel-change metadata
   survives. Locating people from that metadata is impossible.

4. **Essential targeting and verification data is discarded.**
   `controller/agent.py:898–957` keeps dimensions/counts and layer-name strings,
   dropping layer IDs, `activeLayer`, `selectedLayers`, visibility, bounds,
   `hasSelection`, `selectionBounds`, and the app's actual `revision`.
   Upstream `crates/engine/src/inspect.rs:25–85` exposes these fields already.
   `command_run` at `agent.py:783–786` also discards the command's result.
   Opacity 1.0 is rendered as 1% rather than 100%; history length is used as a
   revision even though the app exposes a real revision counter.

5. **Discovery ranking and contracts are degraded before model delivery.**
   `controller/agent.py:805–808` converts ranked hits to a set, then restores
   registry order. `:1124–1129` exposes only the first 12 entries. Strong hits
   can therefore be hidden behind weak ones. Params are cut at 160 characters
   (`:816–822`), cutting `select.rect` before its `ellipse` parameter and
   `layer.setProps` inside its abbreviated blend documentation. Menu paths and
   enabled state are also discarded. The registry itself documents blend modes
   as `Multiply|…`, so truncation removal alone cannot restore the full enum.

6. **There is no bounded recovery from discovery loops.**
   `controller/agent.py:409–415` explicitly permits unlimited repeated reads
   until the total budget is exhausted, including alternating search/inspect/
   look cycles. Errors stop the run immediately (`:512–538`) rather than giving
   the model one informed correction. Follow-up LLM errors are silently caught
   (`:591–592`). Budget exhaustion returns an action-log dump, and completion
   logging always marks `ok=True` (`:606–635`).

7. **Execution state and diagnostics are insufficient.**
   `LlmClient.chat` uses synchronous `httpx.post` inside the async agent loop
   (`controller/llm.py:364–369`), delaying responsiveness/cancellation during a
   provider call. There is no explicit per-document run coordination or
   durable cancelled/failed outcome. Missing B&W/Screen completions may reflect
   cancelled streams, but the retained records cannot prove that.

## Existing app capabilities

These are capability examples, not commands executed during this investigation.

| Intent | Execution route |
|---|---|
| B&W on the duplicate | Resolve/select its layer ID, then `image.adjustments.desaturate {}` or `image.adjustments.blackWhite {}`. Confirm scope and active target; do not convert the entire document's color mode. |
| Screen blend | `layer.setProps {"layer": <resolved-id>, "blend": "Screen"}`. Inspect that same layer and assert its blend is Screen. |
| Circular selection | `select.rect {"x": <x>, "y": <y>, "width": <diameter>, "height": <diameter>, "ellipse": true, "mode": "replace"}` after visual localization in document coordinates. |

The full accepted blend enum is already recorded in
`docs/live-command-inventory.md:147–162`. Elliptical selection is a parameter
of a command labelled “Rectangular Selection,” illustrating why names alone
are insufficient capability documentation.

## Prioritized implementation plan

### P0 — Load an app-specific operating skill

The user's expected behavior is explicit: attaching PhotoCraft, GridCraft, or
another app should load the corresponding skill so the model knows the app's
capabilities and when to use them. Make this a first-class runtime feature of
the Crafter agent, delivered in its provider-bound context.

Each app skill should contain:

- A concise capability map organized by user goals, with scope distinctions
  such as document vs layer vs selection, or workbook vs sheet vs range.
- Target-resolution rules, selection/active-state semantics, coordinate
  systems, units, and relevant prerequisites.
- Verified task recipes explaining when to use each operation, exact command
  IDs, parameter examples, and expected postconditions. Include alternatives
  only where their different effects matter to the user's goal.
- Links to on-demand detailed command contracts and topic guides; keep the
  initial skill compact rather than injecting all 818 commands.
- App/version compatibility metadata, known automation limitations, and
  recovery guidance. Check recipes against the connected app's registry and
  report unavailable capabilities rather than guessing replacements.

For PhotoCraft, the initial skill must cover layer duplication/targeting,
destructive adjustments vs adjustment layers, blend properties, and geometric
selections. It should explicitly teach that Screen is a `layer.setProps`
parameter and an ellipse is `select.rect` with `ellipse: true`. For GridCraft,
cover workbook/sheet/range addressing, values vs formulas, formatting, and
structural changes using its own verified contracts.

Load the skill automatically from the attached app identity before the first
plan. Preserve the skill and loaded topic guidance across the entire run.
Expose topic/contract retrieval to the model for less common operations, with
semantic descriptions of when each topic applies. The live registry remains
the authority for current availability; the skill supplies operating knowledge.
This is application-agent functionality, not OpenCode harness configuration.

Acceptance: inspect the actual outbound model context to prove the correct
app skill is loaded. Execute the four-turn PhotoCraft workflow from its recipes
without repeated broad command discovery; switch to GridCraft and confirm the
appropriate skill and addressing rules are used. Add a contract-consistency
check to detect stale recipe IDs/params when the app version changes.

### P0 — Restore the actual LLM/tool feedback loop

1. Introduce a run-scoped message history: original request, initial structured
   state, assistant tool calls, correlated tool results, and observations.
   Append results for every call before requesting the next model step. Keep
   discovered contracts available across intervening reads; compact older
   history deliberately rather than replacing it with operation summaries.
2. Pass bounded prior conversation context plus structured edit references
   (`last_created_layer_id`, `last_target_layer_id`, verified outcomes).
   Resolve pronouns against live IDs; revalidate IDs before execution.
3. Separate planner data from log-safe summaries. Preserve structured layer
   state, selection state, actual revisions, and useful command return data.
   Normalize units once at the boundary.
4. Add real multimodal delivery for `look`: send image content to a compatible
   model, with image size, document bounds, and coordinate mapping. Prefer a
   canvas render for localization; a window screenshot needs viewport mapping.
   Surface an explicit blocker when the chosen model cannot accept images.

### P1 — Make capability discovery actionable

5. Preserve ranked result order; return a small relevant list with enabled
   state, menu/category, argument summaries, and matched capability fields.
   Add a `command_describe(id)` path providing the complete contract without
   arbitrary character truncation.
6. Provide machine-readable parameter types, complete enums, units, defaults,
   targeting rules, and small execution examples. Use upstream metadata where
   possible; version any verified supplementation for abbreviated registry
   docs. Cover generic capabilities, including property updates and selection
   geometry, rather than hardcoding the user's sentences.
7. Validate arguments against known contracts. Return structured errors and
   allow a bounded correction. Cache discovery metadata per app/version while
   refreshing state-dependent enablement.

### P1 — Progress, verification, and honest outcomes

8. Track both state changes and new information gained. Detect repeated
   discovery cycles across alternating tools. After a configurable small
   no-progress window (initially four calls), require a concrete execution,
   one targeted contract lookup, or an explicit blocker. Do not blindly force
   a mutation just because discovery took too long.
9. Verify request-specific postconditions: target-layer blend, grayscale pixel
   evidence for the target layer, and selection geometry/mask. A changed
   history/hash alone is not proof the user's goal was achieved.
10. Return explicit `succeeded`, `blocked`, `failed`, `cancelled`, or
    `budget_exhausted` outcomes. Separate edits applied from work remaining.
    Preserve terminal outcomes in conversation history. Show meaningful
    progress/verification in the UI instead of repeated revision-only lines;
    correlate tool results by call ID.

### P2 — Runtime reliability and diagnosability

11. Use asynchronous provider I/O and propagate disconnect/cancel through the
    run. Coordinate mutations per live document so a new request cannot race
    an older unfinished edit; define queued/cancelled behavior explicitly.
12. Configure a handler for `crafter.controller` and log structured per-run
    metadata: model, tool/call ID, command ID, candidate IDs/order, contract
    completeness, image-delivery count, actual revisions, no-progress count,
    timings, verification result, and terminal reason. Keep content-bearing
    planner history separate from operational logs. Retain enough run events
    to distinguish “searched only,” “command rejected,” and “edit verified.”

## Acceptance checks

- Repeat the user's four-turn workflow against a disposable document with the
  configured real provider. Duplication creates one copy; B&W affects that
  copy; Screen applies to its ID; a circular selection encloses the intended
  people. Capture actual commands and verified postconditions.
- For simple layer edits, target at most six tool calls per request after
  discovery, with no repeated search/inspect cycle. For visual selection,
  target at most ten, including image observation and verification.
- Protocol-level tests inspect the provider-bound messages: assistant tool
  calls and all correlated results survive multiple steps; prior target IDs
  survive turns; `look` supplies actual image content and coordinate metadata.
- Use the captured real registry and upstream-shaped inspection fixtures.
  Verify search ordering, complete ellipse params, the supplemented Screen
  enum, disabled commands, real revisions, and 0..1 opacity normalization.
  Current blend tests use a richer enum than the real registry and therefore
  do not expose that contract gap (`controller/tests/test_commands.py:75–90`).
- Exercise alternating read-only loops, invalid params with correction,
  unchanged edits, provider failure, cancellation, and a second request on
  the same document. Each must terminate with the correct persisted outcome.

## Scope of this investigation

No application code or live-document edits were made. Existing working-tree
changes were inspected as the current implementation. This report records the
diagnosis and proposed implementation sequence; it does not claim the fixes
are implemented or that the real-provider acceptance workflow has passed.
