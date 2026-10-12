# TC-B-01: Verification Tools (Look/Snapshot/Record/Assert)

**Component**: Verify + Contain
**Epic**: E-001 Crafter Gateway
**V-Model**: SWE3-B-01
**Type**: 🔨 IMPLEMENTATION
**Priority**: P0-Critical
**Estimated Effort**: M
**Dependencies**: TC-A-02 (Phase-1 tools + pilot wiring)
**SW-REQ**: SW-REQ-GW-VERIFY

---

## ⚠️ PROJECT CRITICALITY DISCLAIMER

┌─────────────────────────────────────────────────────────────────────────────┐
│  🚀 MISSION-CRITICAL APPLICATION - READ BEFORE STARTING ANY WORK            │
├─────────────────────────────────────────────────────────────────────────────┤
│  This project is a LIVE PRODUCTION SYSTEM used by real customers.           │
│  • Errors directly impact user trust, data integrity, and revenue.          │
│  • NEVER commit code without understanding its impact.                      │
└─────────────────────────────────────────────────────────────────────────────┘

---

## 🎯 Vision & Criticality

Build the trust primitives: unified render, file-level snapshots, evidence-backed records,
declarative asserts. Without these, agents can silently corrupt documents and narrate success
they did not achieve.

**High Stakes**: Silent document corruption destroys user trust in agentic editing.
**Constraints**: Structural asserts default; visual asserts opt-in with tolerance.

---

## 🏗️ Architectural Context

```
Agent → craft_snapshot → craft_run → craft_look → craft_assert → craft_record
              (TC-A session/roots/auth underneath)
```

See: `project_management/architecture/README.md` for full context.

---

## Traceability

| Level | ID | Artifact |
|-------|-----|---------|
| SYS1 | SYS1-001 | Epic: EPIC_001_CRAFTER_GATEWAY.md |
| SWE1 | SWE1-B | TC: TC-B-00_COMPONENT_DEFINITION.md |
| SWE3 | SWE3-B-01 | This issue |
| SWE4 | — | Unit tests in: `gateway/tests/test_phase2.py` |

---

## 📋 Task List

### 0.0 Read Architecture Documentation [MANDATORY]

- [x] **Read: `project_management/architecture/README.md`**
- [x] **Read: relevant diagrams** in `project_management/architecture/diagrams/`
  (flow-agent-edit-verify, data-model)

### 0.1 Read Predecessor Context [MANDATORY]

- [x] **Read: `TC-B-00_COMPONENT_DEFINITION.md`**
- [x] **Read: `TC-A-02_COMPLETION_REPORT.md`** ← Phase-1 APIs, session/roots model

### 0.2 Run Full Test Suite [MANDATORY GATE 🔴]

- [x] Execute the project's configured test runner (all scopes)
- [x] **Run typecheck** [MANDATORY GATE 🔴]
- [x] **Run linter** [MANDATORY 🔴 from TC-X-02]
- [x] Record baseline; **Gate**: 0 new failures/errors vs. baseline or STOP.

Baseline (Task 0.2): 67 passed; compileall clean; ruff check + format clean.

### 0.3 Tooling Gate (TC-X-01 criterion)

- [x] typecheck + tests + lint clean before handoff to TC-B-02.

### 1. Investigate Requirements

- [x] Read: `08-REQUIRED-TOOLS.md` Phase 2 (`craft_look`, `craft_snapshot`/`craft_restore`,
  `craft_record`, `craft_assert`).

### 1.5 Logging & Observability Integration [MANDATORY CROSS-CUTTING]

- [x] Instrument verify-tool calls, snapshot/restore events, assert outcomes, record validations.
- [x] Reference renders by hash/id in logs — never embed image data. Redact document content.

### 2. Write/Update Requirements

- [x] Record Phase-2 tool contracts in code-adjacent docs.

Contracts live in `gateway/tools_phase2.py` module docstring + per-method
docstrings (params/returns/errors + SW-REQ ref).

### 3. Investigate Architecture

- [x] Review: pilot render entry points per app; snapshot via save/copy to asset store;
  assert evaluation against `doc_inspect` + renders.

FakeAppBackend exposes `doc_inspect` (revision) + `render_preview`
(content_hash) — both used; `engine.restore` probed opportunistically
(absent on fakes → revision returned without backend rollback, documented).

### 4. Implement Code

- [x] `gateway/tools_phase2.py`: `craft_look` (scope/index/region/max_side/detail), `craft_snapshot`/
  `craft_restore` (token + revision), `craft_record` (claim + confidence + evidence; reject
  measured-without-evidence), `craft_assert` (structural default, visual opt-in).
- [x] `gateway/snapshots.py`: snapshot store keyed by session.
- [x] Auto-snapshot policy hook: before batches with >1 destructive step and before `app.save`.
- [x] Wire into `gateway/main.py`.

Shared `SnapshotStore` passed to both `register_phase1_tools` (hook) and
`register_phase2_tools` (restore) so tokens are visible on both paths.

### 5. Create Unit Tests (SWE4) [MANDATORY]

- [x] `gateway/tests/test_phase2.py`: look scopes; snapshot/restore round-trip; record rejection
  of unbacked measured claims; assert structural + visual pass/fail; logger redaction tests.

29 tests, all passing.

### 6. Run Full Test Suite + Coverage [MANDATORY GATE 🔴]

- [x] Execute test runner (all scopes); typecheck 0 new errors; lint 0 new errors.
- [x] **Gate**: 0 new failures allowed. Coverage must not regress.

96 passed (67 → 96, +29, 0 failures); compileall 0 errors; ruff 0 errors.

### 7. Create Documentation

- [x] Tool contract docs; inline API docs; note for closer (data-model rows).

### 8. Write Completion Report & Handoff [MANDATORY]

- [x] Complete `TC-B-01_COMPLETION_REPORT.md`
- [x] **Write handoff section for TC-B-02 team** — MUST include: what was built, decisions +
  deviations, limitations/edge cases, open risks, usage examples, gate results.
- [x] Update `TC-B-00_COMPONENT_DEFINITION.md` with status + new decisions

---

## ⚠️ Constraints

- Default structural asserts; visual asserts require explicit tolerance.
- Renders referenced by hash/id in logs, never embedded.

---

## 📁 Files to Modify

| Action | File Path | Description |
|--------|-----------|-------------|
| Create | `gateway/tools_phase2.py` | Phase-2 tool implementations |
| Create | `gateway/snapshots.py` | Snapshot store |
| Create | `gateway/tests/test_phase2.py` | Phase-2 unit tests |
| Update | `gateway/main.py` | Wire Phase-2 tools |
| Read   | `project_management/_templates/raw_Repository_findings/08-REQUIRED-TOOLS.md` | Phase-2 spec |

---

## ✅ Acceptance Criteria

- [x] All 4 Phase-2 tools work against pilot apps (or documented fakes).
- [x] Unbacked measured claims rejected (tested).
- [x] All unit tests passing (SWE4); coverage not regressed.
- [x] Completion report written with handoff for TC-B-02.
- [x] TC-B-00 updated with status and decisions.
- [x] Logger evidence included.

---

## 📖 Reference Documents

- V-Model Framework: `project_management/_templates/V_MODEL_FRAMEWORK.md`
- Architecture: `project_management/architecture/README.md`
- Epic: `project_management/epics/EPIC_001_CRAFTER_GATEWAY.md`
- Component: `project_management/epics/EPIC_001/TC_B_VERIFY_AND_CONTAIN/TC-B-00_COMPONENT_DEFINITION.md`
- Predecessor Report: `project_management/epics/EPIC_001/TC_A_GATEWAY_CORE/TC-A-02_COMPLETION_REPORT.md`
- SW Requirements: SW-REQ-GW-VERIFY (see TC-B-00)

---

## 🔗 Related Issues

- Depends On: TC-A-02
- Blocks: TC-B-02 (Containment + Docker + closer)
- Related: EPIC_002 chat verify actions

---

## Gate Results (filled during execution)

| Gate | Level | Result | Notes |
|------|-------|--------|-------|
| Pre-check test suite (Task 0.2) | SWE4 | ✅ 67 passed | compileall + ruff clean |
| Post-implementation suite (Task 6) | SWE4 | ✅ 96 passed | 67 → 96 (+29), 0 failures |
| Coverage vs baseline | SWE4 | ✅ no regress | all modules exercised incl. negative/unauthorized/redaction |
| Coverage vs target | ADVISORY | ✅ 29 tests for SW-REQ-GW-VERIFY | recorded for closer's coverage-map |
