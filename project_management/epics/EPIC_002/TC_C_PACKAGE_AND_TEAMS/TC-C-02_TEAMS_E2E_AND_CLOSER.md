# TC-C-02: Scaico Teams E2E + Epic Closer

**Component**: Package + Teams
**Epic**: E-002 Crafter Chat UI
**V-Model**: SWE3-C-02
**Type**: 🔨 IMPLEMENTATION
**Priority**: P1-High
**Estimated Effort**: S
**Dependencies**: TC-C-01 (Packaging)
**SW-REQ**: SW-REQ-PACK

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

Wire Scaico team select end-to-end (key → teams → agent run on pilot doc with verify actions)
and close TC-C **and EPIC_002**. **This issue is the final closer**: no-reviews SWE5 duties +
epic-boundary verification.

**High Stakes**: This is the shippable slice — team-driven agentic editing must work.
**Constraints**: Small issue; mailto fallback + direct mode must both verify.

---

## 🏗️ Architectural Context

```
Settings key → team list (craft_* JSONs) → select → agent session → gateway tools → verify
```

See: `project_management/architecture/README.md` for full context.

---

## Traceability

| Level | ID | Artifact |
|-------|-----|---------|
| SYS1 | SYS1-002 | Epic: EPIC_002_CRAFTER_CHAT_UI.md |
| SWE1 | SWE1-C | TC: TC-C-00_COMPONENT_DEFINITION.md |
| SWE3 | SWE3-C-02 | This issue |
| SWE4 | — | Unit tests in: team select + e2e (mocked) tests |
| SWE5 | self-verify | Integration tests in: team e2e tests |

---

## 📋 Task List

### 0.0 Read Architecture Documentation [MANDATORY]

- [ ] **Read: `project_management/architecture/README.md`**
- [ ] **Read: relevant diagrams** in `project_management/architecture/diagrams/`

### 0.1 Read Predecessor Context [MANDATORY]

- [ ] **Read: `TC-C-00_COMPONENT_DEFINITION.md`**
- [ ] **Read: `TC-C-01_COMPLETION_REPORT.md`** ← predecessor's handoff

### 0.2 Run Full Test Suite [MANDATORY GATE 🔴]

- [ ] Test runner + typecheck + lint (MANDATORY); baseline; Gate: 0 new issues.

### 1. Investigate Requirements

- [ ] Read: `Scaico_Teams/teams/*.json` (team definitions); TC-C-01 handoff.

### 1.5 Logging & Observability Integration [MANDATORY CROSS-CUTTING]

- [ ] Instrument team select + agent runs; never log keys (tested).

### 2. Write/Update Requirements

- [ ] Record team e2e contracts.

### 3. Investigate Architecture

- [ ] Review: team list source, agent session binding, fallback paths.

### 4. Implement Code

- [ ] Team select → agent session wiring against gateway tools (mocked Scaico where needed).
- [ ] Verify mailto fallback + LiteLLM direct mode paths.

### 5. Create Unit Tests (SWE4) [MANDATORY]

- [ ] Team select states; agent run wiring (mocked); fallback paths; key redaction tests.

### 6. Run Full Test Suite + Coverage [MANDATORY GATE 🔴]

- [ ] Runner + typecheck + lint 0 new errors; coverage not regressed.

### 7. Create Documentation

- [ ] Team e2e docs; update TC-C-00.

### 8. TC-C Closer Duties (no-reviews SWE5 inheritance) [MANDATORY]

- [ ] **Gap analysis** of TC-C-01; fix or file known issues.
- [ ] **Integration tests**: packaging + teams e2e (mocked); 0 failures.
- [ ] **Architecture updates**: component-overview (full stack), api-contracts (team contracts),
  requirements-matrix + coverage-map rows for SW-REQ-PACK.
- [ ] **SYS3 runtime smoke**: compose up → chat → team select → agent edit with verify; evidence.
- [ ] **Traceability** rows complete for this TC.

### 9. EPIC_002 Boundary Duties [MANDATORY]

- [ ] Verify all EPIC_002 TCs complete (closers done, reports present).
- [ ] Update `EPIC_002_CRAFTER_CHAT_UI.md`: TC rows → ✅, Status, Last Updated.
- [ ] Update `EPIC_OVERVIEW.md`: E-002 row status.
- [ ] Update `architecture/README.md`: change log + "Last updated by" with this issue.
- [ ] Run full test suite one final time (MANDATORY).

### 10. Write Completion Report & Handoff [MANDATORY]

- [ ] Complete `TC-C-02_COMPLETION_REPORT.md` with closer + epic-boundary evidence.
- [ ] **Handoff**: final state, how to run, known issues, gate results.
- [ ] Update `TC-C-00_COMPONENT_DEFINITION.md`: Status → ✅ Complete.

---

## ⚠️ Constraints

- Keys never logged; fallback paths verified, not just present.

---

## 📁 Files to Modify

| Action | File Path | Description |
|--------|-----------|-------------|
| Create | Team e2e tests | Select + agent run (mocked) |
| Update | `project_management/architecture/diagrams/*.md` | Closer arch updates |
| Update | `project_management/architecture/traceability/*.md` | Closer traceability updates |
| Update | `project_management/epics/EPIC_002_CRAFTER_CHAT_UI.md` | Epic boundary |
| Update | `project_management/epics/EPIC_OVERVIEW.md` | Epic boundary |
| Update | `project_management/architecture/README.md` | Epic boundary |

---

## ✅ Acceptance Criteria

- [ ] Team select → agent run with verify works (mocked Scaico).
- [ ] Fallback + direct paths verified.
- [ ] Gap analysis, integration tests, arch + traceability, smoke evidence complete.
- [ ] EPIC_002 boundary: all TCs ✅, epic + overview + arch README updated.
- [ ] All unit tests passing; coverage not regressed.
- [ ] Completion report written; TC-C-00 → ✅ Complete.
- [ ] Logger evidence (keys never logged — tested) included.

---

## 📖 Reference Documents

- V-Model Framework: `project_management/_templates/V_MODEL_FRAMEWORK.md`
- Architecture: `project_management/architecture/README.md`
- Epic: `project_management/epics/EPIC_002_CRAFTER_CHAT_UI.md`
- Component: `project_management/epics/EPIC_002/TC_C_PACKAGE_AND_TEAMS/TC-C-00_COMPONENT_DEFINITION.md`
- Predecessor Report: `project_management/epics/EPIC_002/TC_C_PACKAGE_AND_TEAMS/TC-C-01_COMPLETION_REPORT.md`
- SW Requirements: SW-REQ-PACK (see TC-C-00)
- Teams: `Scaico_Teams/teams/*.json`

---

## 🔗 Related Issues

- Depends On: TC-C-01
- Blocks: none (final issue)
- Related: EPIC_001 gateway (consumer relationship)

---

## Gate Results (filled during execution)

| Gate | Level | Result | Notes |
|------|-------|--------|-------|
| Pre-check test suite (Task 0.2) | SWE4 | ⬜ PENDING | |
| Post-implementation suite (Task 6) | SWE4 | ⬜ PENDING | |
| Coverage vs baseline | SWE4 | ⬜ PENDING | |
| TC-C integration tests (Task 8) | SWE5 | ⬜ PENDING | |
| SYS3 smoke (Task 8) | SYS3 | ⬜ PENDING | |
