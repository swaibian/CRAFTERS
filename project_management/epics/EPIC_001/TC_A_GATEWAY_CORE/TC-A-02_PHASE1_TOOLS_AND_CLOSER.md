# TC-A-02: Phase-1 Tools + Pilot Wiring + TC Closer

**Component**: Gateway Core
**Epic**: E-001 Crafter Gateway
**V-Model**: SWE3-A-02
**Type**: 🔨 IMPLEMENTATION
**Priority**: P0-Critical
**Estimated Effort**: M
**Dependencies**: TC-A-01 (Gateway service + auth + allowlists)
**SW-REQ**: SW-REQ-GW-CORE

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

Implement the Phase 1 tool surface and wire the three pilot apps, proving the gateway
architecture end-to-end. **This issue is the TC-A closer**: it inherits the no-reviews SWE5
duties — gap analysis, integration tests, architecture/traceability updates, and the SYS3
runtime smoke.

**High Stakes**: Without working pilot wiring, EPIC_002 chat UI has nothing to connect to.
**Constraints**: Pilot-only (photocraft, pdfcraft, gridcraft); generic design for the other 9.

---

## 🏗️ Architectural Context

```
Agent → craft_apps/status/run/run_tool/app_call → backends.py → photocraft/pdfcraft/gridcraft-cli mcp
```

See: `project_management/architecture/README.md` for full context.

---

## Traceability

| Level | ID | Artifact |
|-------|-----|---------|
| SYS1 | SYS1-001 | Epic: EPIC_001_CRAFTER_GATEWAY.md |
| SWE1 | SWE1-A | TC: TC-A-00_COMPONENT_DEFINITION.md |
| SWE3 | SWE3-A-02 | This issue |
| SWE4 | — | Unit tests in: `gateway/tests/test_phase1.py` |
| SWE5 | self-verify | Integration tests in: `gateway/tests/test_integration_tc_a.py` |

---

## 📋 Task List

### 0.0 Read Architecture Documentation [MANDATORY]

- [x] **Read: `project_management/architecture/README.md`**
- [x] **Read: relevant diagrams** in `project_management/architecture/diagrams/`

### 0.1 Read Predecessor Context [MANDATORY]

- [x] **Read: `TC-A-00_COMPONENT_DEFINITION.md`**
- [x] **Read: `TC-A-01_COMPLETION_REPORT.md`** ← predecessor's handoff

### 0.2 Run Full Test Suite [MANDATORY GATE 🔴]

- [x] Execute the project's configured test runner (all scopes)
- [x] **Run typecheck** [MANDATORY GATE 🔴]
- [x] **Run linter** [MANDATORY 🔴 from TC-X-02]
- [x] Record baseline; **Gate**: 0 new failures/errors vs. baseline or STOP.

### 1. Investigate Requirements

- [x] Read: `08-REQUIRED-TOOLS.md` Phase 1 (`craft_apps`, `craft_status`, `craft_run`,
  `craft_run_tool`, `craft_app_call`).
- [x] Read: TC-A-01 handoff (auth/session/backend APIs to build on).

### 1.5 Logging & Observability Integration [MANDATORY CROSS-CUTTING]

- [x] Instrument Phase-1 tool ingress/egress + proxied app responses through project logger.
- [x] Redact params that may carry document content / image data; allow-list safe fields.

### 2. Write/Update Requirements

- [x] Record Phase-1 tool contracts (params, auth, errors) in code-adjacent docs.

### 3. Investigate Architecture

- [x] Review: pilot CLI invocation (`photocraft-cli mcp`, `pdfcraft-cli mcp`, `gridcraft-cli mcp`);
  generic app registry so other apps need no code changes.

### 4. Implement Code

- [x] `gateway/tools_phase1.py`: `craft_apps`, `craft_status`, `craft_run`, `craft_run_tool`,
  `craft_app_call` with allowlist enforcement + session roots.
- [x] Pilot registry: app id → CLI command, default args, capability flags.
- [x] Wire tools into `gateway/main.py` FastMCP app.

### 5. Create Unit Tests (SWE4) [MANDATORY]

- [x] `gateway/tests/test_phase1.py`: each tool happy path + error cases; allowlist denial;
  roots confinement; logger redaction tests.

### 6. Run Full Test Suite + Coverage [MANDATORY GATE 🔴]

- [x] Execute test runner (all scopes); typecheck 0 new errors; lint 0 new errors.
- [x] **Gate**: 0 new failures allowed. Coverage must not regress.

### 7. Create Documentation

- [x] Tool contract docs; inline API docs.
- [x] Update `TC-A-00` status + decisions.

### 8. TC-A Closer Duties (no-reviews SWE5 inheritance) [MANDATORY]

- [x] **Gap analysis**: review TC-A-01 completion report for bugs, inconsistencies, missed
  requirements; fix or file as known issues.
- [x] **Integration tests**: `gateway/tests/test_integration_tc_a.py` — auth + tools + pilot
  backends cross-module; 0 failures.
- [x] **Architecture updates**: component-overview (gateway block), api-contracts (Phase-1
  sequences), requirements-matrix + coverage-map rows for SW-REQ-GW-CORE.
- [x] **SYS3 runtime smoke**: start gateway (stdio + http), call `craft_status` against pilot
  CLIs (or documented fakes), verify output; record evidence.
- [x] **Traceability**: matrix + coverage rows complete for this TC.

### 9. Write Completion Report & Handoff [MANDATORY]

- [x] Complete `TC-A-02_COMPLETION_REPORT.md` with closer evidence (gaps, integration results,
  arch updates, smoke evidence).
- [x] **Handoff for TC-B-01**: Phase-1 tool APIs, session/roots model, auth contract, usage
  examples, gate results.
- [x] Update `TC-A-00_COMPONENT_DEFINITION.md`: Status → ✅ Complete.

---

## ⚠️ Constraints

- Pilot apps only; generic registry (no per-app code beyond registry entries).
- No token/secret/PII in logs (tested).

---

## 📁 Files to Modify

| Action | File Path | Description |
|--------|-----------|-------------|
| Create | `gateway/tools_phase1.py` | Phase-1 tool implementations |
| Create | `gateway/tests/test_phase1.py` | Phase-1 unit tests |
| Create | `gateway/tests/test_integration_tc_a.py` | TC-A integration tests |
| Update | `gateway/main.py` | Wire Phase-1 tools into FastMCP app |
| Update | `project_management/architecture/diagrams/*.md` | Closer arch updates |
| Update | `project_management/architecture/traceability/*.md` | Closer traceability updates |

---

## ✅ Acceptance Criteria

- [x] All 5 Phase-1 tools work against pilot CLIs (or documented fakes).
- [x] Gap analysis complete; integration tests passing; arch + traceability updated.
- [x] SYS3 smoke evidence recorded.
- [x] All unit tests passing (SWE4); coverage not regressed.
- [x] Completion report written with handoff for TC-B-01.
- [x] TC-A-00 Status → ✅ Complete.
- [x] Logger evidence included.

---

## 📖 Reference Documents

- V-Model Framework: `project_management/_templates/V_MODEL_FRAMEWORK.md`
- Architecture: `project_management/architecture/README.md`
- Epic: `project_management/epics/EPIC_001_CRAFTER_GATEWAY.md`
- Component: `project_management/epics/EPIC_001/TC_A_GATEWAY_CORE/TC-A-00_COMPONENT_DEFINITION.md`
- Predecessor Report: `project_management/epics/EPIC_001/TC_A_GATEWAY_CORE/TC-A-01_COMPLETION_REPORT.md`
- SW Requirements: SW-REQ-GW-CORE (see TC-A-00)
- Research: `project_management/_templates/raw_Repository_findings/08-REQUIRED-TOOLS.md`

---

## 🔗 Related Issues

- Depends On: TC-A-01
- Blocks: TC-B-01 (Verification tools + containment)
- Related: EPIC_002 chat UI

---

## Gate Results (filled during execution)

| Gate | Level | Result | Notes |
|------|-------|--------|-------|
| Pre-check test suite (Task 0.2) | SWE4 | ✅ 47 passed (TC-A-01 baseline) | |
| Post-implementation suite (Task 6) | SWE4 | ✅ 67 passed, 0 failed | |
| Coverage vs baseline | SWE4 | ✅ 47 → 67, no regressions | |
| TC-A integration tests (Task 8) | SWE5 | ✅ 6 passed | |
| SYS3 smoke (Task 8) | SYS3 | ✅ PASS stdio + http craft_status | |
