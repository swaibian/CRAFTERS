# TC-C-01: pdfcraft AccessKit + photocraft canvasRect

**Component**: Accessibility Refs
**Epic**: E-001 Crafter Gateway
**V-Model**: SWE3-C-01
**Type**: 🔨 IMPLEMENTATION
**Priority**: P1-High
**Estimated Effort**: M
**Dependencies**: TC-B-02 (hardened gateway to build on)
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

Deliver the two reference accessibility implementations: pdfcraft's AccessKit tree over MCP,
and photocraft's document↔screen mapping. These close the highest-value perception gaps and
prove the contribution pattern.

**High Stakes**: Without these, agents pixel-hunt instead of addressing widgets/coordinates.
**Constraints**: Upstream PR shape must be minimal and reviewable; gateway shim fallback if PRs
stall.

---

## 🏗️ Architectural Context

```
pdfcraft control channel (AccessKit) → gateway proxy → MCP tool
photocraft views[] (zoom/centre) → gateway/perception.py → query_map backing
```

See: `project_management/architecture/README.md` for full context.

---

## Traceability

| Level | ID | Artifact |
|-------|-----|---------|
| SYS1 | SYS1-001 | Epic: EPIC_001_CRAFTER_GATEWAY.md |
| SWE1 | SWE1-C | TC: TC-C-00_COMPONENT_DEFINITION.md |
| SWE3 | SWE3-C-01 | This issue |
| SWE4 | — | Unit tests in: `gateway/tests/test_perception.py` |

---

## 📋 Task List

### 0.0 Read Architecture Documentation [MANDATORY]

- [ ] **Read: `project_management/architecture/README.md`**
- [ ] **Read: relevant diagrams** in `project_management/architecture/diagrams/`

### 0.1 Read Predecessor Context [MANDATORY]

- [ ] **Read: `TC-C-00_COMPONENT_DEFINITION.md`**
- [ ] **Read: `TC-B-02_COMPLETION_REPORT.md`** ← hardened gateway handoff

### 0.2 Run Full Test Suite [MANDATORY GATE 🔴]

- [ ] Execute test runner; typecheck (MANDATORY); lint (MANDATORY from TC-X-02).
- [ ] Record baseline; **Gate**: 0 new failures/errors or STOP.

### 0.3 Tooling Gate (TC-X-01 criterion)

- [ ] typecheck + tests + lint clean before handoff to TC-C-02.

### 1. Investigate Requirements

- [ ] Read: `06-PERCEPTION.md` (AccessKit + canvasRect gaps); `01-RESEARCH-FINDINGS.md` §7.

### 1.5 Logging & Observability Integration [MANDATORY CROSS-CUTTING]

- [ ] Instrument perception proxy calls; redact any text content that may be PII.

### 2. Write/Update Requirements

- [ ] Record AccessKit + canvasRect contracts.

### 3. Investigate Architecture

- [ ] Review: pdfcraft control-channel AccessKit surface; photocraft `views[]` zoom/centre model.

### 4. Implement Code

- [ ] `gateway/perception.py`: AccessKit proxy tool + canvasRect synthesis + `query_map` backing.
- [ ] Upstream PR drafts (pdfcraft, photocraft) in reviewable shape; gateway shim if stalled.

### 5. Create Unit Tests (SWE4) [MANDATORY]

- [ ] `gateway/tests/test_perception.py`: mapping math; proxy happy/error paths; redaction tests.

### 6. Run Full Test Suite + Coverage [MANDATORY GATE 🔴]

- [ ] Execute test runner; typecheck + lint 0 new errors; coverage not regressed.

### 7. Create Documentation

- [ ] Perception contract docs; PR descriptions; note for closer.

### 8. Write Completion Report & Handoff [MANDATORY]

- [ ] Complete `TC-C-01_COMPLETION_REPORT.md`
- [ ] **Write handoff section for TC-C-02 team** — MUST include: what was built, decisions +
  deviations, limitations/edge cases, open risks, usage examples, gate results.
- [ ] Update `TC-C-00_COMPONENT_DEFINITION.md` with status + new decisions

---

## ⚠️ Constraints

- Upstream PRs minimal and reviewable; gateway shim fallback documented.
- No PII in logs (widget text may carry it — redact).

---

## 📁 Files to Modify

| Action | File Path | Description |
|--------|-----------|-------------|
| Create | `gateway/perception.py` | AccessKit proxy + canvasRect synthesis |
| Create | `gateway/tests/test_perception.py` | Perception unit tests |
| Create | Upstream PR drafts | pdfcraft + photocraft contributions |
| Read   | `project_management/_templates/raw_Repository_findings/06-PERCEPTION.md` | Gap spec |

---

## ✅ Acceptance Criteria

- [ ] AccessKit tree reachable via gateway MCP tool (or shim with PR pending).
- [ ] Document↔screen mapping resolves for photocraft views (tested).
- [ ] All unit tests passing; coverage not regressed.
- [ ] Completion report with handoff for TC-C-02; TC-C-00 updated.
- [ ] Logger evidence included.

---

## 📖 Reference Documents

- V-Model Framework: `project_management/_templates/V_MODEL_FRAMEWORK.md`
- Architecture: `project_management/architecture/README.md`
- Epic: `project_management/epics/EPIC_001_CRAFTER_GATEWAY.md`
- Component: `project_management/epics/EPIC_001/TC_C_ACCESSIBILITY_REFS/TC-C-00_COMPONENT_DEFINITION.md`
- Predecessor Report: `project_management/epics/EPIC_001/TC_B_VERIFY_AND_CONTAIN/TC-B-02_COMPLETION_REPORT.md`
- SW Requirements: SW-REQ-A11Y (see TC-C-00)

---

## 🔗 Related Issues

- Depends On: TC-B-02
- Blocks: TC-C-02 (Pattern + closer)
- Related: EPIC_002 perception consumers

---

## Gate Results (filled during execution)

| Gate | Level | Result | Notes |
|------|-------|--------|-------|
| Pre-check test suite (Task 0.2) | SWE4 | ⬜ PENDING | |
| Post-implementation suite (Task 6) | SWE4 | ⬜ PENDING | |
| Coverage vs baseline | SWE4 | ⬜ PENDING | |
| Coverage vs target | ADVISORY | ⬜ PENDING | |
