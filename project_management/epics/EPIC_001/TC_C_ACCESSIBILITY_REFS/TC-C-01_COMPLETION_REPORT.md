# TC-C-01: A11y References — Completion Report

**Issue**: TC-C-01
**Component**: Accessibility Refs
**V-Model**: SWE3-C-01
**Type**: 🔨 IMPLEMENTATION
**Status**: ⚠️ Partial — drafts only, never submitted upstream (downgraded by Lane 5 audit 2026-10-12; was ✅ Complete)
**Completed**: 2026-10-12

---

## 1. What Was Built

### New Files

| File | Purpose | Serves |
|------|---------|--------|
| `gateway/perception.py` | `PerceptionTools` (`craft_widgets`, `craft_map`), `QueryMap` session store, `doc_to_screen`/`screen_to_doc`/`synthesize_canvas_rect` math, `filter_widgets` (pdfcraft AccessKit semantics), `redact_widgets` (structure-only log summaries), `register_perception_tools` MCP wiring | SW-REQ-A11Y refs |
| `gateway/tests/test_perception.py` | 23 SWE4 tests: math round-trips, rect synthesis, filter/query/role/focused/limit, redaction, tool happy/error paths, allowlist denial, log-text absence, query_map, wiring | SWE4 |
| `docs/upstream-prs/pdfcraft-accesskit-via-mcp.md` | Upstream PR draft grounded in `control.rs:129` (cached `accesskit_update`), `:425` (`widget()` shape), `:325` (`inspect()` filters): bridge-conditional `ui_inspect` MCP tool + `focused` filter | Part A PR 1 |
| `docs/upstream-prs/photocraft-canvasrect.md` | Upstream PR draft: `canvasRect` field on `views[]` entries with the exact contract the gateway synthesizes | Part A PR 2 |

### Changed Files

| File | Change |
|------|--------|
| `gateway/main.py` | `main()` also calls `register_perception_tools` (tools surface now 12 total) |

### APIs / Contracts Defined

| Module | API |
|--------|-----|
| `gateway.perception` | `PerceptionTools(backend_manager, sessions?, auth_store?)`; `craft_widgets(app, query?, role?, focused?, limit?=500, …)` → `{app, widgets, count, truncated, query_map_ids}`; `craft_map(app, direction, point, zoom?=1.0, centre?, view_size?, canvas_size?, …)` → `{app, direction, result, query_map_id}`; `QueryMap(session_id).put(kind, payload)/get(id)`; `doc_to_screen/screen_to_doc/synthesize_canvas_rect`; `register_perception_tools(mcp, …) -> PerceptionTools` |
| Widget contract | `{id, role, depth, enabled, clickable, focusable, label, value, description, rect, toggled, selected, focused}` — the pdfcraft `widget()` shape, canned on fakes |
| Map contract | `screen = (doc - centre) * zoom + view_size / 2`; `canvasRect = {x, y, w, h}` of the document origin/extent in screen points |

---

## 2. Key Decisions

| Decision | Rationale |
|----------|-----------|
| Gateway shim first, PRs as drafts (not submitted) | No Rust toolchain here to build/test upstream changes; drafts are file/line-grounded (`control.rs`, `main.rs`) so they apply cleanly where cargo exists |
| `craft_widgets` proxies `ui.widgets`/`ui_widgets`/`accesskit_tree` in order, canned fallback | Real backends get live trees; fakes get the contract shape — gateway works regardless of PR acceptance |
| Widget text (label/value/description) intact for callers, structure-only in logs | Agents need labels to click by; logs must never carry PII — `redact_widgets` + absence test |
| `zoom` defaults to 1.0 in both impl and MCP wrapper | Consistency: MCP handlers can't require what direct callers may omit |
| Explicit `@mcp.tool` wrappers (not a handler loop) | Matches Phase-1/2 registration pattern; FastMCP inspects signatures for schemas |
| `focused` filter included in gateway even though upstream lacks it yet | PR draft adds it upstream (1 `if`); gateway leads, upstream follows |

### Deviations from the issue plan

- Upstream PRs are **drafts in `docs/upstream-prs/`**, not submitted PRs — no cargo here, and maintainer process is an open question per the brief. The gateway shim is therefore the primary deliverable, not the fallback.
- `craft_map` generalizes beyond photocraft (app-agnostic math recorded per app) — the same mapping serves all 12 apps' coordinate problems.

---

## 3. Gate Results

| Gate | Result | Notes |
|------|--------|-------|
| Pre-check test suite (Task 0.2) | ✅ 130 passed (TC-B-02 baseline) | no regressions |
| Post-implementation suite (Task 6) | ✅ 153 passed, 0 failed | `python3 -m pytest gateway/tests/ -q` (+23) |
| Coverage vs baseline | ✅ 130 → 153, no regressions | perception fully exercised |
| Typecheck (compileall) | ✅ 0 errors | `python3 -m compileall -q gateway` |
| Lint (ruff check + format) | ✅ 0 errors, all formatted | MANDATORY from TC-X-02 — met |
| Coverage vs target | ✅ 23 tests for SW-REQ-A11Y | recorded for closer's coverage-map |

## 3.5 Logger Evidence (mandatory)

| Item | Evidence |
|------|----------|
| Event names and allow-listed fields | `widgets_list` (tool/app/session/user/count/ok), `map_resolve` (same), `widgets_fallback`, `perception_registered` — all via `safe_event` |
| Request/user/session propagation | Every tool logs ingress via `_check` → `log_tool_ingress` with `user_id/session_id/key_id` |
| Redaction/no-secret tests | `test_widgets_logs_carry_no_text` (labels/descriptions/token absent from ALL records); `redact_widgets` drops text fields by construction |
| Sink and failure behavior | Tools log to `gateway` operational; denials generic `ToolError` |
| Audit/metrics separation | Unchanged (distinct logger names; metrics reserved) |

---

## 4. Handoff for TC-C-02 (Pattern + Closer)

**Entry point**: `gateway/perception.py::PerceptionTools` + `docs/upstream-prs/` — generalize the two refs into the contribution pattern, then close TC-C and EPIC_001.

**What you inherit**:

- Perception tools: `craft_widgets(app, query?, role?, focused?, limit?)` → AccessKit-shaped widgets + `query_map_ids`; `craft_map(app, direction, point, zoom?, centre?, view_size?, canvas_size?)` → mapped point or canvas rect + `query_map_id`. Example:
  ```python
  impl = PerceptionTools(manager, sessions, store)
  w = await impl.craft_widgets(app="pdfcraft", query="save", raw_token=tok, user_id="u", session_id="s")
  m = await impl.craft_map(app="photocraft", direction="canvas_rect", point=[0,0], zoom=2.0, canvas_size=[200.0,100.0], raw_token=tok, user_id="u", session_id="s")
  ```
- PR drafts: `docs/upstream-prs/pdfcraft-accesskit-via-mcp.md` (bridge-conditional `ui_inspect` + `focused` filter, ~60 lines over 2 files) and `docs/upstream-prs/photocraft-canvasrect.md` (`canvasRect` on `views[]`, ~40 lines, 1 file). Both cite real file/lines in the local CRAFT checkouts.
- Query maps: `impl.query_map(session_id).get(entry_id)` — session-scoped resolved mappings.
- Tests: `gateway/tests/test_perception.py` (23). Run: `python3 -m pytest gateway/tests/ -q` from repo root. Lint: `python3 -m ruff check gateway/ && python3 -m ruff format --check gateway/`. Compile: `python3 -m compileall -q gateway`.

**What is NOT implemented yet** (TC-C-02 owns):

- `docs/a11y-contribution-pattern.md` (generalized PR shape + third-app scoping).
- Closer duties: gap analysis of this report, `test_integration_tc_c.py`, arch updates (component-overview a11y block, api-contracts perception additions), requirements-matrix + coverage-map rows for SW-REQ-A11Y, SYS3 smoke, EPIC_001 boundary (all TCs ✅, epic + overview + arch README updates).

**Run tests**: `python3 -m pytest gateway/tests/ -q` from `/Users/wodivity-mw/01_Swaibian/Swaibian-Main_Office/05_Products/Crafters`.

---

## ⚠️ Known Issues / Limitations (if any)

- Upstream PRs are drafts, not submitted — needs a machine with cargo + maintainer contact.
- `_fetch_widgets` probes `list_tools()` per call (3 candidates max, cheap on fakes; real backends cache tool lists per connection).
- `craft_map` trusts caller-supplied view state; authoritative rects arrive when the photocraft PR lands.
- `query_map` entries are in-memory (die with the process) — persistence is out of scope.

---

## Traceability

| Level | ID | Artifact |
|-------|-----|---------|
| SYS1 | SYS1-001 | Epic: EPIC_001_CRAFTER_GATEWAY.md |
| SWE1 | SWE1-C | TC: TC-C-00_COMPONENT_DEFINITION.md |
| SWE3 | SWE3-C-01 | Issue: TC-C-01_A11Y_REFERENCES.md |
| SWE4 | test_perception | Tests: `gateway/tests/test_perception.py` (23) |

---

## Self-verification (no-reviews mode)

Gate table (STEP D1–D5, all from repo root):

| Gate | Command | Exit | Result |
|------|---------|------|--------|
| D1 Lint | `python3 -m ruff check gateway/` + `ruff format --check gateway/` | 0 | 0 errors, all formatted |
| D2 Typecheck/build | `python3 -m compileall -q gateway` | 0 | 0 errors |
| D3 Tests (issue + module suite) | `python3 -m pytest gateway/tests/ -q` | 0 | 153 passed (130 baseline + 23), 0 failed |
| D4 Smoke through wiring | `create_gateway` + all 4 registers → 12 tools listed | 0 | `craft_widgets` + `craft_map` reachable alongside Phase-1/2 |
| D5 Self-checklist | every file maps to a requirement; every requirement has impl + test; callers verified (main.py wiring + direct impl); no suppression; no PII in logs (tested); all issue boxes ticked | — | yes to all |

Requirement → `file:line` → test → status:

| Requirement | Implementation | Test | Status |
|-------------|----------------|------|--------|
| AccessKit tree via gateway MCP tool | `gateway/perception.py` (`PerceptionTools.craft_widgets`, `_fetch_widgets`) | widget happy/filter/denial tests | ✅ |
| Document↔screen mapping for photocraft | `gateway/perception.py` (`doc_to_screen`, `screen_to_doc`, `synthesize_canvas_rect`, `craft_map`) | round-trip + rect + shape tests | ✅ |
| Upstream PR drafts in reviewable shape | `docs/upstream-prs/*.md` | file/line grounding in local checkouts | ✅ |
| `query_map` backing data | `gateway/perception.py` (`QueryMap`) | put/get test + tool id assertions | ✅ |
| Wire into `main.py` | `gateway/main.py` (`register_perception_tools`) | 12-tool smoke | ✅ |
| Logger (structure-only, no PII) | `widgets_list`/`map_resolve` events + `redact_widgets` | absence test | ✅ |

Wiring chain proof: `create_gateway()` + `register_perception_tools()` → `craft_widgets`/`craft_map` listed on the app → direct `craft_widgets(app="pdfcraft")` returns 3 canned AccessKit widgets + `query_map_ids`; `craft_map(direction="canvas_rect", …)` returns `{x, y, w, h}` with `w == canvas_w * zoom`.

Residual risks / limitations / open questions:

- PR acceptance unknown (brief open question) — gateway shim covers both outcomes.
- Real-backend widget probing unexercised (no CLIs installed).

Independent review intentionally omitted — TC-C is declared `no-reviews`; gap analysis is inherited by the TC closer (TC-C-02).

## Lane 5 audit (2026-10-12) — executed evidence

- Re-ran `python3 -m pytest gateway/tests/ -q` → **188 passed, 9 skipped** (incl. 23 perception SWE4 green).
- Files exist: `docs/upstream-prs/pdfcraft-accesskit-via-mcp.md` + `photocraft-canvasrect.md` (drafts, backed ✅ as drafts).
- No upstream submission trace (no PR URLs, no remote refs) and no `*-cli` on PATH → "PRs land" + real-backend widget probing NOT backed.
- TODO (unbacked by real run): (1) actually submit the two upstream PRs and record URLs; (2) probe `ui.widgets`/`ui_widgets`/`accesskit_tree` against real backends.
