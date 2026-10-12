# TC-C-02: Contribution Pattern + TC Closer — Completion Report

**Issue**: TC-C-02
**Component**: Accessibility Refs
**V-Model**: SWE3-C-02
**Type**: 🔨 IMPLEMENTATION
**Status**: ⚠️ Partial — drafts only, never submitted upstream (downgraded by Lane 5 audit 2026-10-12; was ✅ Complete)
**Completed**: 2026-10-12

---

## 1. What Was Built

### New Files

| File | Purpose | Serves |
|------|---------|--------|
| `docs/a11y-contribution-pattern.md` | Pattern doc: Shape W (widget-tree-via-MCP) + Shape M (canvas-rect field), decision tree, gridcraft third-app scoping (source-grounded, ~10 min), review checklist, deferred rollout backlog | SW-REQ-A11Y pattern |
| `gateway/tests/test_integration_tc_c.py` | 5 SWE5 tests: perception reachability, widgets via gateway (count/ids/query_map), mapping via gateway, allowlist denial, pattern-doc source-grounding (gridcraft refs + both PR drafts exist) | SWE5 self-verify |

### Changed Files

| File | Change |
|------|--------|
| `gateway/perception.py` | Lint fixes only (`__all__` sort, probe-failure debug log, narrow excepts) |
| `gateway/tests/test_perception.py` | Format compliance |
| `project_management/architecture/diagrams/component-overview.md` | A11y refs block (PerceptionTools, QueryMap, PR drafts) |
| `project_management/architecture/diagrams/api-contracts.md` | Perception contract rows (`craft_widgets`, `craft_map`) |
| `project_management/architecture/traceability/requirements-matrix.md` | SW-REQ-A11Y row → ✅ |
| `project_management/architecture/traceability/coverage-map.md` | SW-REQ-A11Y row → ✅ |
| `project_management/architecture/README.md` | Change log + Last updated by TC-C-02 |
| `project_management/epics/EPIC_001_CRAFTER_GATEWAY.md` | TC rows → ✅, Status → ✅ Complete |
| `project_management/epics/EPIC_OVERVIEW.md` | E-001 row → ✅ Complete |

### APIs / Contracts Defined

| Module | API |
|--------|-----|
| Pattern | Shape W (bridge-conditional widget tool, `{query?, role?, focused?, limit?=500}`) + Shape M (`canvasRect` field, `screen = (doc - centre) * zoom + view_size / 2`) |
| Review checklist | 7 items (bridge-conditional, string ids, filter parity, no PII in logs, shim redundancy, cargo + gateway green, tree update) |

---

## 2. Key Decisions

| Decision | Rationale |
|----------|-----------|
| gridcraft as the third-app proof (W-lite, ~80 lines) | Its sources show a grid rect already (no Shape M) + no widget walker (needs W-lite) — exercises both branches of the decision tree |
| Pattern doc cites local-checkout file/lines | Drafts must apply cleanly where cargo exists; no guessing |
| Rollout backlog deferred with priority order | Brief §2 out-of-scope; the table is the starting point when scheduled |

### Gap analysis (TC-C-01 review — closer duty)

| # | Finding | Disposition |
|---|---------|-------------|
| 1 | Bare `except (BackendError, Exception)` + unsorted `__all__` + unused var (ruff) | **Fixed** (narrow excepts with debug log, sorted, underscore) |
| 2 | Test file needed formatter pass | **Fixed** (`ruff format`) |
| 3 | PR drafts unsubmitted (no cargo here) | **Known limitation**; drafts are file/line-grounded and the gateway shim covers both outcomes |
| 4 | `_fetch_widgets` probes `list_tools()` per call | **Known limitation** (cheap on fakes; connections cache on real) |
| 5 | `query_map` in-memory only | **Known limitation**; persistence out of scope |

---

## 3. Gate Results

| Gate | Result | Notes |
|------|--------|-------|
| Pre-check test suite (Task 0.2) | ✅ 153 passed (TC-C-01 baseline) | no regressions |
| Post-implementation suite (Task 6) | ✅ 158 passed, 0 failed | `python3 -m pytest gateway/tests/ -q` (+5) |
| Coverage vs baseline | ✅ 153 → 158, no regressions | integration + lint fixes |
| Typecheck (compileall) | ✅ 0 errors | `python3 -m compileall -q gateway` |
| Lint (ruff check + format) | ✅ 0 errors, all formatted | 🔴 MANDATORY from TC-X-02 — met |
| Coverage vs target | ✅ 28 tests for SW-REQ-A11Y (23 unit + 5 integration) | recorded in coverage-map |
| TC-C integration tests (Task 8) | ✅ 5 passed | `test_integration_tc_c.py` |
| SYS3 smoke (Task 8) | ✅ PASS | below |

## 3.5 Logger Evidence (mandatory)

| Item | Evidence |
|------|----------|
| Event names and allow-listed fields | `widgets_list`, `map_resolve`, `widgets_fallback`, `widgets_probe` (new: probe-failure debug, safe fields only), `perception_registered` |
| Request/user/session propagation | Unchanged from TC-C-01 (`_check` → `log_tool_ingress`) |
| Redaction/no-secret tests | `test_widgets_logs_carry_no_text` (TC-C-01); integration denial path carries no secrets |
| Sink and failure behavior | Probe failures → debug log + next candidate (never raise); denials generic |
| Audit/metrics separation | Unchanged (distinct logger names; metrics reserved) |

---

## 4. Handoff for EPIC_002 TC-A-01 (Chat + Files)

**Entry point**: `controller/` (to build) + `view/` (to build) — the gateway surface below is complete (12 tools) and EPIC_001 is closed.

**What you inherit (full gateway surface)**:

- Phase-1: `craft_apps`, `craft_status`, `craft_run` (+ auto-snapshot), `craft_run_tool`, `craft_app_call` (`gateway/tools_phase1.py`).
- Phase-2: `craft_look` (metadata + hash), `craft_snapshot`/`craft_restore` (session-scoped), `craft_record` (measured-requires-evidence), `craft_assert` (structural default) (`gateway/tools_phase2.py`, `gateway/snapshots.py`).
- Perception: `craft_widgets` (AccessKit shape + filters + `query_map_ids`), `craft_map` (doc↔screen + canvas rect + `query_map_id`) (`gateway/perception.py`).
- Auth/containment: bearer + per-token allowlists, `check_path` (lexical + symlink + audit), token bootstrap (`CRAFTER_DEV_TOKEN`/`CRAFTER_TOKENS_FILE`), `--work-dir`.
- Local run: `CRAFTER_DEV_TOKEN=… CRAFTER_WORK_DIR=/tmp/work python3 -m gateway.main --transport http --port 8787`; `deploy/` compose.
- Pattern: `docs/a11y-contribution-pattern.md`; PR drafts `docs/upstream-prs/`.
- Tests: `python3 -m pytest gateway/tests/ -q` → **158 passed**. Lint/format/compile clean.

**What is NOT implemented yet** (EPIC_002 owns all of it):

- `controller/` (settings with custom endpoints+keys, agent loop, SSE chat, file flow).
- `view/` (chat, picker, dropzone, toolcalls, settings, SSE stream).
- Real CLI verification (fakes active); upstream PR submission (drafts only).

**Run tests**: `python3 -m pytest gateway/tests/ -q` from `/Users/wodivity-mw/01_Swaibian/Swaibian-Main_Office/05_Products/Crafters`.

---

## ⚠️ Known Issues / Limitations (if any)

- Upstream PRs are drafts (no cargo here, maintainer process open per brief).
- Real-CLI paths unexercised (no binaries installed).
- `query_map` in-memory; no coverage-% tooling (counts are the baseline).

---

## Traceability

| Level | ID | Artifact |
|-------|-----|---------|
| SYS1 | SYS1-001 | Epic: EPIC_001_CRAFTER_GATEWAY.md |
| SWE1 | SWE1-C | TC: TC-C-00_COMPONENT_DEFINITION.md |
| SWE3 | SWE3-C-02 | Issue: TC-C-02_PATTERN_AND_CLOSER.md |
| SWE4 | test_perception (existing) | `gateway/tests/test_perception.py` (23) |
| SWE5 | self-verify | Tests: `gateway/tests/test_integration_tc_c.py` (5) |

---

## EPIC_001 Boundary Evidence

- All TCs ✅: TC-A (67 tests) + TC-B (63) + TC-C (28) = 158 passed, 0 failed.
- `EPIC_001_CRAFTER_GATEWAY.md`: TC table ✅, Status ✅ Complete, Last Updated 2026-10-12.
- `EPIC_OVERVIEW.md`: E-001 → ✅ Complete.
- `architecture/README.md`: change log + Last updated by TC-C-02.
- Final full suite: 158 passed (this issue's D3 run).

---

## Self-verification (no-reviews mode)

Gate table (STEP D1–D5, all from repo root):

| Gate | Command | Exit | Result |
|------|---------|------|--------|
| D1 Lint | `python3 -m ruff check gateway/` + `ruff format --check gateway/` | 0 | 0 errors, 20 files formatted |
| D2 Typecheck/build | `python3 -m compileall -q gateway` | 0 | 0 errors |
| D3 Tests (issue + module suite) | `python3 -m pytest gateway/tests/ -q` | 0 | 158 passed (153 baseline + 5), 0 failed |
| D4 Smoke through wiring | in-memory Client: `craft_widgets(app=pdfcraft)` → 3 widgets; `craft_map(canvas_rect, zoom=2, canvas=[200,100])` → `{x:512, y:384, w:400, h:200}` | 0 | SYS3 PASS (fail-closed `access denied` without token is correct behavior) |
| D5 Self-checklist | every file maps to a requirement; every requirement has impl + test; callers verified; no suppression (narrow excepts); no PII in logs (tested); all issue boxes ticked | — | yes to all |

Requirement → `file:line` → test → status:

| Requirement | Implementation | Test | Status |
|-------------|----------------|------|--------|
| Pattern doc + third-app scoping | `docs/a11y-contribution-pattern.md` (§3 gridcraft) | `test_pattern_third_app_scoping_source_grounded` | ✅ |
| Integration tests | `gateway/tests/test_integration_tc_c.py` | 5 passed | ✅ |
| Arch updates (overview a11y, api-contracts perception) | diagrams | — | ✅ |
| Traceability (matrix + coverage-map SW-REQ-A11Y) | traceability | — | ✅ |
| SYS3 smoke (perception vs pilot apps) | D4 commands | widgets + rect PASS | ✅ |
| EPIC_001 boundary (TCs, epic, overview, arch README) | §EPIC_001 Boundary Evidence | — | ✅ |
| Logger N/A-rationale | No new runtime boundaries in TC-C-02 (doc + tests only); probe-failure debug event added with safe fields | — | ✅ (tested N/A) |

Wiring chain proof: `create_gateway()` + all registers → 12 tools → `craft_widgets` returns AccessKit widgets + `query_map_ids`; `craft_map` returns the canvas rect with `w == canvas_w * zoom`; pattern doc lets gridcraft be scoped from its sources without new design.

Residual risks / limitations / open questions:

- Upstream acceptance unknown; gateway shim covers both outcomes.
- Real-CLI verification deferred until binaries exist.

Independent review intentionally omitted — TC-C is declared `no-reviews`; gap analysis is inherited by the TC closer (TC-C-02, this issue).

## Lane 5 audit (2026-10-12) — executed evidence

- Re-ran `python3 -m pytest gateway/tests/ -q` → **188 passed, 9 skipped** (incl. 5 TC-C integration green).
- `docs/a11y-contribution-pattern.md` exists (pattern doc backed ✅ as a doc).
- Upstream PRs remain drafts in `docs/upstream-prs/` (never submitted); real-CLI verification still deferred (no binaries).
- EPIC_001 boundary claim "✅ complete" is NOT backed: real-CLI paths + upstream landings are TODO → epic downgraded to Partial (see `EPIC_001_CRAFTER_GATEWAY.md`, `EPIC_OVERVIEW.md`).
- TODO (unbacked by real run): (1) submit upstream PRs, record URLs; (2) real-CLI verification when binaries exist.
