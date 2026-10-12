# TC-C-02: Contribution Pattern + TC Closer

**Component**: Accessibility Refs
**Epic**: E-001 Crafter Gateway
**V-Model**: SWE3-C-02
**Type**: 🔨 IMPLEMENTATION
**Priority**: P1-High
**Estimated Effort**: S
**Dependencies**: TC-C-01 (A11y references)
**SW-REQ**: SW-REQ-A11Y

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

Write the repeatable contribution pattern doc and close TC-C (and with it, EPIC_001's last TC).
**This issue is the TC-C closer and the EPIC_001 final closer**: inherits no-reviews SWE5
duties — gap analysis, integration tests, architecture/traceability updates, SYS3 smoke — plus
epic-boundary verification.

**High Stakes**: Without the pattern, the 10-app rollout needs new design work later.
**Constraints**: Small issue; pattern must let a third app be scoped without new design.

---

## 🏗️ Architectural Context

```
TC-C-01 refs → docs/a11y-contribution-pattern.md → future per-app PRs
```

See: `project_management/architecture/README.md` for full context.

---

## Traceability

| Level | ID | Artifact |
|-------|-----|---------|
| SYS1 | SYS1-001 | Epic: EPIC_001_CRAFTER_GATEWAY.md |
| SWE1 | SWE1-C | TC: TC-C-00_COMPONENT_DEFINITION.md |
| SWE3 | SWE3-C-02 | This issue |
| SWE4 | — | Unit tests in: existing `gateway/tests/` (no new suite expected) |
| SWE5 | self-verify | Integration tests in: `gateway/tests/test_integration_tc_c.py` |

---

## 📋 Task List

### 0.0 Read Architecture Documentation [MANDATORY]

- [ ] **Read: `project_management/architecture/README.md`**
- [ ] **Read: relevant diagrams** in `project_management/architecture/diagrams/`

### 0.1 Read Predecessor Context [MANDATORY]

- [ ] **Read: `TC-C-00_COMPONENT_DEFINITION.md`**
- [ ] **Read: `TC-C-01_COMPLETION_REPORT.md`** ← predecessor's handoff

### 0.2 Run Full Test Suite [MANDATORY GATE 🔴]

- [ ] Execute test runner; typecheck; lint (MANDATORY from TC-X-02).
- [ ] Record baseline; **Gate**: 0 new failures/errors or STOP.

### 1. Investigate Requirements

- [ ] Read: TC-C-01 handoff (ref implementations to generalise).

### 1.5 Logging & Observability Integration [MANDATORY CROSS-CUTTING]

- [ ] Verify no new runtime boundaries; document N/A rationale if none, with test.

### 2. Write/Update Requirements

- [ ] Record pattern scope (what a per-app PR must contain).

### 3. Investigate Architecture

- [ ] Review: what generalised vs. what stayed app-specific in TC-C-01.

### 4. Implement Code

- [ ] `docs/a11y-contribution-pattern.md`: PR shape, test expectations, review checklist,
  third-app scoping exercise.
- [ ] Minor hardening from TC-C-01 known issues (if any).

### 5. Create Unit Tests (SWE4) [MANDATORY]

- [ ] Pattern doc validated (third-app scoping walkthrough recorded); existing suites green.

### 6. Run Full Test Suite + Coverage [MANDATORY GATE 🔴]

- [ ] Execute test runner; typecheck + lint 0 new errors; coverage not regressed.

### 7. Create Documentation

- [ ] Pattern doc; update TC-C-00.

### 8. TC-C Closer Duties (no-reviews SWE5 inheritance) [MANDATORY]

- [ ] **Gap analysis** of TC-C-01; fix or file known issues.
- [ ] **Integration tests** `test_integration_tc_c.py`: perception proxy + mapping end-to-end.
- [ ] **Architecture updates**: component-overview (a11y block), api-contracts (perception
  additions), requirements-matrix + coverage-map rows for SW-REQ-A11Y.
- [ ] **SYS3 runtime smoke**: perception tools against pilot apps; record evidence.
- [ ] **Traceability** rows complete for this TC.

### 9. EPIC_001 Boundary Duties [MANDATORY]

- [ ] Verify all EPIC_001 TCs complete (TC-A/B/C closers done, reports present).
- [ ] Update `EPIC_001_CRAFTER_GATEWAY.md`: TC rows → ✅, Status, Last Updated.
- [ ] Update `EPIC_OVERVIEW.md`: E-001 row status.
- [ ] Update `architecture/README.md`: change log + "Last updated by" with this issue.
- [ ] Run full test suite one final time (MANDATORY).

### 10. Write Completion Report & Handoff [MANDATORY]

- [ ] Complete `TC-C-02_COMPLETION_REPORT.md` with closer + epic-boundary evidence.
- [ ] **Handoff for EPIC_002 TC-A-01**: gateway surface, perception additions, pattern doc,
  usage examples, gate results.
- [ ] Update `TC-C-00_COMPONENT_DEFINITION.md`: Status → ✅ Complete.

---

## ⚠️ Constraints

- Small scope; pattern doc is the deliverable alongside closer duties.

---

## 📁 Files to Modify

| Action | File Path | Description |
|--------|-----------|-------------|
| Create | `docs/a11y-contribution-pattern.md` | Repeatable upstream PR shape |
| Create | `gateway/tests/test_integration_tc_c.py` | TC-C integration tests |
| Update | `project_management/architecture/diagrams/*.md` | Closer arch updates |
| Update | `project_management/architecture/traceability/*.md` | Closer traceability updates |
| Update | `project_management/epics/EPIC_001_CRAFTER_GATEWAY.md` | Epic boundary |
| Update | `project_management/epics/EPIC_OVERVIEW.md` | Epic boundary |
| Update | `project_management/architecture/README.md` | Epic boundary |

---

## ✅ Acceptance Criteria

- [ ] Pattern doc complete; third-app scoping walkthrough recorded.
- [ ] Gap analysis, integration tests, arch + traceability, smoke evidence complete.
- [ ] EPIC_001 boundary: all TCs ✅, epic + overview + arch README updated.
- [ ] All unit tests passing; coverage not regressed.
- [ ] Completion report with handoff for EPIC_002; TC-C-00 → ✅ Complete.
- [ ] Logger evidence (or tested N/A rationale) included.

---

## 📖 Reference Documents

- V-Model Framework: `project_management/_templates/V_MODEL_FRAMEWORK.md`
- Architecture: `project_management/architecture/README.md`
- Epic: `project_management/epics/EPIC_001_CRAFTER_GATEWAY.md`
- Component: `project_management/epics/EPIC_001/TC_C_ACCESSIBILITY_REFS/TC-C-00_COMPONENT_DEFINITION.md`
- Predecessor Report: `project_management/epics/EPIC_001/TC_C_ACCESSIBILITY_REFS/TC-C-01_COMPLETION_REPORT.md`
- SW Requirements: SW-REQ-A11Y (see TC-C-00)

---

## 🔗 Related Issues

- Depends On: TC-C-01
- Blocks: EPIC_002 TC-A-01 (Chat UI consumer)
- Related: future 10-app rollout (out of scope)

---

## Gate Results (filled during execution)

| Gate | Level | Result | Notes |
|------|-------|--------|-------|
| Pre-check test suite (Task 0.2) | SWE4 | ⬜ PENDING | |
| Post-implementation suite (Task 6) | SWE4 | ⬜ PENDING | |
| Coverage vs baseline | SWE4 | ⬜ PENDING | |
| TC-C integration tests (Task 8) | SWE5 | ⬜ PENDING | |
| SYS3 smoke (Task 8) | SYS3 | ⬜ PENDING | |
