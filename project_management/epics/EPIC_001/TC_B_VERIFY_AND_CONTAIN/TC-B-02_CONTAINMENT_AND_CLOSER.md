# TC-B-02: Containment + Docker + TC Closer

**Component**: Verify + Contain
**Epic**: E-001 Crafter Gateway
**V-Model**: SWE3-B-02
**Type**: 🔨 IMPLEMENTATION
**Priority**: P0-Critical
**Estimated Effort**: M
**Dependencies**: TC-B-01 (Verification tools)
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

Harden containment (roots enforced on every file path) and ship the containerised local run.
**This issue is the TC-B closer**: inherits no-reviews SWE5 duties — gap analysis, integration
tests, architecture/traceability updates, SYS3 smoke.

**High Stakes**: 8/12 apps lack confinement — without enforced roots + container, agents can
escape the work dir.
**Constraints**: Roots enforced on ALL file-bearing tools; Docker run documented.

---

## 🏗️ Architectural Context

```
Every file path → roots check → allow/deny → audit log
Docker: gateway + pilot CLIs + mounted work dir → local run
```

See: `project_management/architecture/README.md` for full context.

---

## Traceability

| Level | ID | Artifact |
|-------|-----|---------|
| SYS1 | SYS1-001 | Epic: EPIC_001_CRAFTER_GATEWAY.md |
| SWE1 | SWE1-B | TC: TC-B-00_COMPONENT_DEFINITION.md |
| SWE3 | SWE3-B-02 | This issue |
| SWE4 | — | Unit tests in: `gateway/tests/test_containment.py` |
| SWE5 | self-verify | Integration tests in: `gateway/tests/test_integration_tc_b.py` |

---

## 📋 Task List

### 0.0 Read Architecture Documentation [MANDATORY]

- [ ] **Read: `project_management/architecture/README.md`**
- [ ] **Read: relevant diagrams** in `project_management/architecture/diagrams/`

### 0.1 Read Predecessor Context [MANDATORY]

- [ ] **Read: `TC-B-00_COMPONENT_DEFINITION.md`**
- [ ] **Read: `TC-B-01_COMPLETION_REPORT.md`** ← predecessor's handoff

### 0.2 Run Full Test Suite [MANDATORY GATE 🔴]

- [ ] Execute test runner; typecheck; lint (MANDATORY from TC-X-02).
- [ ] Record baseline; **Gate**: 0 new failures/errors or STOP.

### 1. Investigate Requirements

- [ ] Read: `04-SECURITY.md` (raw findings) §3 containment; TC-B-01 handoff.

### 1.5 Logging & Observability Integration [MANDATORY CROSS-CUTTING]

- [ ] Log roots allow/deny decisions (audit stream); redact paths outside roots to parent only.

### 2. Write/Update Requirements

- [ ] Record containment contract + Docker run contract.

### 3. Investigate Architecture

- [ ] Review: path interception points in backends + tools; Docker base image with pilot CLIs.

### 4. Implement Code

- [ ] Enforce roots on every file-bearing tool path (open/save/export/render-to-path/snapshot).
- [ ] `deploy/Dockerfile` + `deploy/docker-compose.yml`: gateway + pilot CLIs, work-dir mount,
  documented local run.
- [ ] Audit log for allow/deny decisions.

### 5. Create Unit Tests (SWE4) [MANDATORY]

- [ ] `gateway/tests/test_containment.py`: traversal, absolute-outside-root, symlink escape,
  missing parent, read/write independence; audit log redaction tests.

### 6. Run Full Test Suite + Coverage [MANDATORY GATE 🔴]

- [ ] Execute test runner; typecheck + lint 0 new errors; coverage not regressed.

### 7. Create Documentation

- [ ] Containment + Docker run docs; update TC-B-00.

### 8. TC-B Closer Duties (no-reviews SWE5 inheritance) [MANDATORY]

- [ ] **Gap analysis** of TC-B-01; fix or file known issues.
- [ ] **Integration tests** `test_integration_tc_b.py`: verify tools + containment + snapshots
  cross-module; 0 failures.
- [ ] **Architecture updates**: data-model (SNAPSHOT/RECORD/EVIDENCE), flow-agent-edit-verify,
  requirements-matrix + coverage-map rows for SW-REQ-GW-VERIFY.
- [ ] **SYS3 runtime smoke**: start containerised gateway, snapshot → edit → look → assert →
  record against a pilot app; record evidence.
- [ ] **Traceability** rows complete for this TC.

### 9. Write Completion Report & Handoff [MANDATORY]

- [ ] Complete `TC-B-02_COMPLETION_REPORT.md` with closer evidence.
- [ ] **Handoff for TC-C-01**: verify-tool APIs, containment contract, Docker run, usage
  examples, gate results.
- [ ] Update `TC-B-00_COMPONENT_DEFINITION.md`: Status → ✅ Complete.

---

## ⚠️ Constraints

- Roots enforced everywhere file paths flow; no bypass flags.
- Docker run must work from a fresh checkout with documented prereqs.

---

## 📁 Files to Modify

| Action | File Path | Description |
|--------|-----------|-------------|
| Create | `gateway/tests/test_containment.py` | Containment unit tests |
| Create | `gateway/tests/test_integration_tc_b.py` | TC-B integration tests |
| Create | `deploy/Dockerfile` | Gateway + pilot CLI image |
| Create | `deploy/docker-compose.yml` | Local run composition |
| Update | `gateway/backends.py`, `gateway/tools_phase*.py` | Roots enforcement |
| Update | `project_management/architecture/diagrams/*.md` | Closer arch updates |
| Update | `project_management/architecture/traceability/*.md` | Closer traceability updates |

---

## ✅ Acceptance Criteria

- [ ] Escape attempts rejected on all file tools (tested).
- [ ] Docker local run documented and smoke-tested.
- [ ] Gap analysis, integration tests, arch + traceability, smoke evidence complete.
- [ ] All unit tests passing; coverage not regressed.
- [ ] Completion report with handoff for TC-C-01; TC-B-00 → ✅ Complete.
- [ ] Logger evidence included.

---

## 📖 Reference Documents

- V-Model Framework: `project_management/_templates/V_MODEL_FRAMEWORK.md`
- Architecture: `project_management/architecture/README.md`
- Epic: `project_management/epics/EPIC_001_CRAFTER_GATEWAY.md`
- Component: `project_management/epics/EPIC_001/TC_B_VERIFY_AND_CONTAIN/TC-B-00_COMPONENT_DEFINITION.md`
- Predecessor Report: `project_management/epics/EPIC_001/TC_B_VERIFY_AND_CONTAIN/TC-B-01_COMPLETION_REPORT.md`
- SW Requirements: SW-REQ-GW-VERIFY (see TC-B-00)

---

## 🔗 Related Issues

- Depends On: TC-B-01
- Blocks: TC-C-01 (Accessibility refs)
- Related: EPIC_002 packaging (reuses Docker pattern)

---

## Gate Results (filled during execution)

| Gate | Level | Result | Notes |
|------|-------|--------|-------|
| Pre-check test suite (Task 0.2) | SWE4 | ⬜ PENDING | |
| Post-implementation suite (Task 6) | SWE4 | ⬜ PENDING | |
| Coverage vs baseline | SWE4 | ⬜ PENDING | |
| TC-B integration tests (Task 8) | SWE5 | ⬜ PENDING | |
| SYS3 smoke (Task 8) | SYS3 | ⬜ PENDING | |
