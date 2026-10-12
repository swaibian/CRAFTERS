# TC-A-02: Toolcall View + Verify Actions + TC Closer

**Component**: Chat + Files
**Epic**: E-002 Crafter Chat UI
**V-Model**: SWE3-A-02
**Type**: 🔨 IMPLEMENTATION
**Priority**: P0-Critical
**Estimated Effort**: M
**Dependencies**: TC-A-01 (Chat thread + files)
**SW-REQ**: SW-REQ-CHAT

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

Render toolcalls inline with detail view plus snapshot/restore + verify actions on agent edits.
**This issue is the TC-A closer**: inherits no-reviews SWE5 duties — gap analysis, integration
tests, arch/traceability updates, SYS3 smoke.

**High Stakes**: Without visible toolcalls + verify actions, users cannot trust agent edits.
**Constraints**: Detail view must not leak secrets; verify actions call gateway tools.

---

## 🏗️ Architectural Context

```
Chat message → ToolcallView (inline + collapsible) → verify actions → gateway snapshot/assert/record
```

See: `project_management/architecture/README.md` for full context.

---

## Traceability

| Level | ID | Artifact |
|-------|-----|---------|
| SYS1 | SYS1-002 | Epic: EPIC_002_CRAFTER_CHAT_UI.md |
| SWE1 | SWE1-A | TC: TC-A-00_COMPONENT_DEFINITION.md |
| SWE3 | SWE3-A-02 | This issue |
| SWE4 | — | Unit tests in: `view/src/.../*.test.tsx` |
| SWE5 | self-verify | Integration tests: chat + gateway (mocked) |

---

## 📋 Task List

### 0.0 Read Architecture Documentation [MANDATORY]

- [ ] **Read: `project_management/architecture/README.md`**
- [ ] **Read: relevant diagrams** in `project_management/architecture/diagrams/`

### 0.1 Read Predecessor Context [MANDATORY]

- [ ] **Read: `TC-A-00_COMPONENT_DEFINITION.md`**
- [ ] **Read: `TC-A-01_COMPLETION_REPORT.md`** ← predecessor's handoff

### 0.2 Run Full Test Suite [MANDATORY GATE 🔴]

- [ ] Test runner + typecheck + lint (MANDATORY from TC-X-02); baseline; Gate: 0 new issues.

### 1. Investigate Requirements

- [ ] Read: TC-A-01 handoff; discovery brief stories #2, #7.

### 1.5 Logging & Observability Integration [MANDATORY CROSS-CUTTING]

- [ ] Instrument toolcall render + verify actions; redact params that may carry content.

### 2. Write/Update Requirements

- [ ] Record toolcall/verify contracts.

### 3. Investigate Architecture

- [ ] Review: gateway snapshot/assert/record call shapes for verify actions.

### 4. Implement Code

- [ ] `ToolcallView.tsx`: inline blocks + collapsible detail (params, result, status).
- [ ] Verify actions: snapshot, restore, assert-run, record-view on agent edits.
- [ ] Working pill / pending states.

### 5. Create Unit Tests (SWE4) [MANDATORY]

- [ ] Toolcall render states; verify-action calls (mocked gateway); redaction tests.

### 6. Run Full Test Suite + Coverage [MANDATORY GATE 🔴]

- [ ] Runner + typecheck + lint 0 new errors; coverage not regressed.

### 7. Create Documentation

- [ ] Component docs; update TC-A-00.

### 8. TC-A Closer Duties (no-reviews SWE5 inheritance) [MANDATORY]

- [ ] **Gap analysis** of TC-A-01; fix or file known issues.
- [ ] **Integration tests**: chat + file flow + toolcalls against mocked gateway; 0 failures.
- [ ] **Architecture updates**: flow-chat-file-open, api-contracts (chat), requirements-matrix +
  coverage-map rows for SW-REQ-CHAT.
- [ ] **SYS3 runtime smoke**: start view (+ gateway stub), drop file → open → chat render →
  verify action; record evidence.
- [ ] **Traceability** rows complete for this TC.

### 9. Write Completion Report & Handoff [MANDATORY]

- [ ] Complete `TC-A-02_COMPLETION_REPORT.md` with closer evidence.
- [ ] **Handoff for TC-B-01**: chat components, gateway call shapes, usage examples, gates.
- [ ] Update `TC-A-00_COMPONENT_DEFINITION.md`: Status → ✅ Complete.

---

## ⚠️ Constraints

- No secrets in toolcall detail view (tested).
- Verify actions must degrade gracefully when gateway unreachable.

---

## 📁 Files to Modify

| Action | File Path | Description |
|--------|-----------|-------------|
| Create | `view/src/.../ToolcallView.tsx` | Toolcall rendering + detail |
| Create | Verify actions | Snapshot/restore/assert/record UI |
| Update | `view/src/.../CrafterChat.tsx` | Wire toolcall view in |
| Update | `project_management/architecture/diagrams/*.md` | Closer arch updates |
| Update | `project_management/architecture/traceability/*.md` | Closer traceability updates |

---

## ✅ Acceptance Criteria

- [ ] Toolcalls render inline + detail; verify actions work (mocked gateway).
- [ ] Gap analysis, integration tests, arch + traceability, smoke evidence complete.
- [ ] All unit tests passing; coverage not regressed.
- [ ] Completion report with handoff for TC-B-01; TC-A-00 → ✅ Complete.
- [ ] Logger evidence included.

---

## 📖 Reference Documents

- V-Model Framework: `project_management/_templates/V_MODEL_FRAMEWORK.md`
- Architecture: `project_management/architecture/README.md`
- Epic: `project_management/epics/EPIC_002_CRAFTER_CHAT_UI.md`
- Component: `project_management/epics/EPIC_002/TC_A_CHAT_AND_FILES/TC-A-00_COMPONENT_DEFINITION.md`
- Predecessor Report: `project_management/epics/EPIC_002/TC_A_CHAT_AND_FILES/TC-A-01_COMPLETION_REPORT.md`
- SW Requirements: SW-REQ-CHAT (see TC-A-00)

---

## 🔗 Related Issues

- Depends On: TC-A-01
- Blocks: TC-B-01 (Streaming + settings)
- Related: TC-B streaming attaches here

---

## Gate Results (filled during execution)

| Gate | Level | Result | Notes |
|------|-------|--------|-------|
| Pre-check test suite (Task 0.2) | SWE4 | ⬜ PENDING | |
| Post-implementation suite (Task 6) | SWE4 | ⬜ PENDING | |
| Coverage vs baseline | SWE4 | ⬜ PENDING | |
| TC-A integration tests (Task 8) | SWE5 | ⬜ PENDING | |
| SYS3 smoke (Task 8) | SYS3 | ⬜ PENDING | |
