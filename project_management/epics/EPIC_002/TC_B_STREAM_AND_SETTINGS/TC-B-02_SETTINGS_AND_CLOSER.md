# TC-B-02: Settings (Scaico/LiteLLM) + TC Closer

**Component**: Stream + Settings
**Epic**: E-002 Crafter Chat UI
**V-Model**: SWE3-B-02
**Type**: 🔨 IMPLEMENTATION
**Priority**: P0-Critical
**Estimated Effort**: M
**Dependencies**: TC-B-01 (Streaming + pictures)
**SW-REQ**: SW-REQ-STREAM

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

Settings surface: Scaico key + team select, `contact@swaibian.com` mailto fallback, LiteLLM
direct toggle, gateway endpoint config. **This issue is the TC-B closer**: no-reviews SWE5
duties — gap analysis, integration tests, arch/traceability updates, SYS3 smoke.

**High Stakes**: Key handling mistakes leak credentials; missing fallback dead-ends evaluators.
**Constraints**: Keys server-side only; per-user budgets for LiteLLM direct.

---

## 🏗️ Architectural Context

```
Settings → Scaico key validate → team select populates
         → no key → mailto CTA + LiteLLM direct toggle
         → gateway endpoint config
```

See: `project_management/architecture/README.md` for full context.

---

## Traceability

| Level | ID | Artifact |
|-------|-----|---------|
| SYS1 | SYS1-002 | Epic: EPIC_002_CRAFTER_CHAT_UI.md |
| SWE1 | SWE1-B | TC: TC-B-00_COMPONENT_DEFINITION.md |
| SWE3 | SWE3-B-02 | This issue |
| SWE4 | — | Unit tests in: `view/src/.../*.test.tsx` |
| SWE5 | self-verify | Integration tests: settings + stream (mocked) |

---

## 📋 Task List

### 0.0 Read Architecture Documentation [MANDATORY]

- [ ] **Read: `project_management/architecture/README.md`**
- [ ] **Read: relevant diagrams** in `project_management/architecture/diagrams/`

### 0.1 Read Predecessor Context [MANDATORY]

- [ ] **Read: `TC-B-00_COMPONENT_DEFINITION.md`**
- [ ] **Read: `TC-B-01_COMPLETION_REPORT.md`** ← predecessor's handoff

### 0.2 Run Full Test Suite [MANDATORY GATE 🔴]

- [ ] Test runner + typecheck + lint (MANDATORY); baseline; Gate: 0 new issues.

### 1. Investigate Requirements

- [ ] Read: epic 003 key validation + epic 009 LLM settings (reference); TC-B-01 handoff.

### 1.5 Logging & Observability Integration [MANDATORY CROSS-CUTTING]

- [ ] Instrument settings changes; never log keys (store server-side; test denial paths).

### 2. Write/Update Requirements

- [ ] Record settings contracts (key storage, team select, fallback, budgets).

### 3. Investigate Architecture

- [ ] Review: key validation endpoint; team list source (`craft_*` team JSONs via gateway/Scaico).

### 4. Implement Code

- [ ] `Settings.tsx`: Scaico key input + validation + team dropdown; mailto CTA
  (`contact@swaibian.com`); LiteLLM direct toggle + budget display; gateway endpoint field.
- [ ] Wire settings into stream path selection (Scaico vs direct).

### 5. Create Unit Tests (SWE4) [MANDATORY]

- [ ] Settings render states; key validation (mocked); team populate; fallback CTA; no-key
  logging tests (keys never in logs/errors).

### 6. Run Full Test Suite + Coverage [MANDATORY GATE 🔴]

- [ ] Runner + typecheck + lint 0 new errors; coverage not regressed.

### 7. Create Documentation

- [ ] Settings docs; update TC-B-00.

### 8. TC-B Closer Duties (no-reviews SWE5 inheritance) [MANDATORY]

- [ ] **Gap analysis** of TC-B-01; fix or file known issues.
- [ ] **Integration tests**: settings + streaming + pictures mocked end-to-end; 0 failures.
- [ ] **Architecture updates**: api-contracts (SSE + settings), requirements-matrix +
  coverage-map rows for SW-REQ-STREAM.
- [ ] **SYS3 runtime smoke**: view with mocked backends — stream a reply, send picture, toggle
  settings; record evidence.
- [ ] **Traceability** rows complete for this TC.

### 9. Write Completion Report & Handoff [MANDATORY]

- [ ] Complete `TC-B-02_COMPLETION_REPORT.md` with closer evidence.
- [ ] **Handoff for TC-C-01**: settings APIs, stream hook, usage examples, gate results.
- [ ] Update `TC-B-00_COMPONENT_DEFINITION.md`: Status → ✅ Complete.

---

## ⚠️ Constraints

- Keys server-side only; never in view state persisted to logs.
- Mailto fallback always visible when no key (no dead ends).

---

## 📁 Files to Modify

| Action | File Path | Description |
|--------|-----------|-------------|
| Create | `view/src/.../Settings.tsx` | Settings surface |
| Update | Stream path selection | Scaico vs direct wiring |
| Update | `project_management/architecture/diagrams/*.md` | Closer arch updates |
| Update | `project_management/architecture/traceability/*.md` | Closer traceability updates |

---

## ✅ Acceptance Criteria

- [ ] Settings work: key → teams; no key → mailto + direct mode.
- [ ] Gap analysis, integration tests, arch + traceability, smoke evidence complete.
- [ ] All unit tests passing; coverage not regressed.
- [ ] Completion report with handoff for TC-C-01; TC-B-00 → ✅ Complete.
- [ ] Logger evidence included (keys never logged — tested).

---

## 📖 Reference Documents

- V-Model Framework: `project_management/_templates/V_MODEL_FRAMEWORK.md`
- Architecture: `project_management/architecture/README.md`
- Epic: `project_management/epics/EPIC_002_CRAFTER_CHAT_UI.md`
- Component: `project_management/epics/EPIC_002/TC_B_STREAM_AND_SETTINGS/TC-B-00_COMPONENT_DEFINITION.md`
- Predecessor Report: `project_management/epics/EPIC_002/TC_B_STREAM_AND_SETTINGS/TC-B-01_COMPLETION_REPORT.md`
- SW Requirements: SW-REQ-STREAM (see TC-B-00)

---

## 🔗 Related Issues

- Depends On: TC-B-01
- Blocks: TC-C-01 (Packaging + teams)
- Related: EPIC_001 auth (key patterns)

---

## Gate Results (filled during execution)

| Gate | Level | Result | Notes |
|------|-------|--------|-------|
| Pre-check test suite (Task 0.2) | SWE4 | ⬜ PENDING | |
| Post-implementation suite (Task 6) | SWE4 | ⬜ PENDING | |
| Coverage vs baseline | SWE4 | ⬜ PENDING | |
| TC-B integration tests (Task 8) | SWE5 | ⬜ PENDING | |
| SYS3 smoke (Task 8) | SYS3 | ⬜ PENDING | |
