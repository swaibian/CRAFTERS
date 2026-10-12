# TC-A-01: Chat Thread + Tool Picker + File Flow

**Component**: Chat + Files
**Epic**: E-002 Crafter Chat UI
**V-Model**: SWE3-A-01
**Type**: 🔨 IMPLEMENTATION
**Priority**: P0-Critical
**Estimated Effort**: M
**Dependencies**: EPIC_001 gateway surface (TC-C-02 handoff)
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

Build the chat thread, tool picker, and drag/drop file-open flow so a user can select an app,
drop a file, and start chatting about the opened document. The primary user journey (story #1).

**High Stakes**: If file-open fails, the whole app has no entry point.
**Constraints**: Desktop-first; markdown+GFM/KaTeX; keyboard operable.

---

## 🏗️ Architectural Context

```
ToolPicker → dropzone → session roots → gateway open → chat enabled (bound document)
Chat thread ← markdown render ← (streaming attaches in TC-B)
```

See: `project_management/architecture/README.md` for full context.

---

## Traceability

| Level | ID | Artifact |
|-------|-----|---------|
| SYS1 | SYS1-002 | Epic: EPIC_002_CRAFTER_CHAT_UI.md |
| SWE1 | SWE1-A | TC: TC-A-00_COMPONENT_DEFINITION.md |
| SWE3 | SWE3-A-01 | This issue |
| SWE4 | — | Unit tests in: `view/src/.../*.test.tsx` |

---

## 📋 Task List

### 0.0 Read Architecture Documentation [MANDATORY]

- [ ] **Read: `project_management/architecture/README.md`**
- [ ] **Read: relevant diagrams** in `project_management/architecture/diagrams/`
  (component-overview, flow-chat-file-open)

### 0.1 Read Predecessor Context [MANDATORY]

- [ ] **Read: `TC-A-00_COMPONENT_DEFINITION.md`**
- [ ] **Read: EPIC_001 `TC-C-02_COMPLETION_REPORT.md`** ← gateway surface handoff

### 0.2 Run Full Test Suite [MANDATORY GATE 🔴]

- [ ] Detect view test runner (vitest expected) + typecheck (`tsc -b`) + lint (oxlint).
- [ ] Record baseline: total tests, passing, failing, skipped, coverage %, typecheck errors, lint errors
- [ ] **Gate**: new failures/errors vs. baseline → STOP.

### 0.3 Tooling Gate (TC-X-01 criterion)

- [ ] typecheck + tests + lint clean before handoff to TC-A-02.

### 1. Investigate Requirements

- [ ] Read: discovery brief §5 (layout, interactions); swaibian-one `SharedChatSection.tsx`
  (reference patterns only).

### 1.5 Logging & Observability Integration [MANDATORY CROSS-CUTTING]

- [ ] View logging at chat/file-flow boundaries via project logger; no `console.*`.
- [ ] Never log prompts, document content, image data, tokens.

### 2. Write/Update Requirements

- [ ] Record chat/file-flow contracts in code-adjacent docs.

### 3. Investigate Architecture

- [ ] Review: route wiring (`/crafter`), gateway client, session roots upload path.

### 4. Implement Code

- [ ] `CrafterChat.tsx`: thread, composer (text; picture input attaches in TC-B), route wiring.
- [ ] `ToolPicker.tsx`: app picker + dropzone → open-in-app → chat enablement.
- [ ] Markdown rendering (GFM/KaTeX) for messages.

### 5. Create Unit Tests (SWE4) [MANDATORY]

- [ ] Component tests: picker selection, dropzone→open flow (mocked gateway), markdown render,
  keyboard operation, logger redaction tests.

### 6. Run Full Test Suite + Coverage [MANDATORY GATE 🔴]

- [ ] Test runner + `tsc -b` 0 new errors + lint clean (advisory on 01); coverage not regressed.

### 7. Create Documentation

- [ ] Component docs; note for closer (flow diagram rows).

### 8. Write Completion Report & Handoff [MANDATORY]

- [ ] Complete `TC-A-01_COMPLETION_REPORT.md`
- [ ] **Write handoff section for TC-A-02 team** — MUST include: what was built, decisions +
  deviations, limitations/edge cases, open risks, usage examples, gate results.
- [ ] Update `TC-A-00_COMPONENT_DEFINITION.md` with status + new decisions

---

## ⚠️ Constraints

- Reuse by reference only — do NOT modify swaibian-one code.
- No prompts/content/image data/tokens in logs (tested).

---

## 📁 Files to Modify

| Action | File Path | Description |
|--------|-----------|-------------|
| Create | `view/src/.../CrafterChat.tsx` | Chat thread + route |
| Create | `view/src/.../ToolPicker.tsx` | Picker + dropzone + open flow |
| Create | `view/src/.../*.test.tsx` | Component tests |

---

## ✅ Acceptance Criteria

- [ ] Picker + dropzone + open-in-app + chat enablement work (mocked gateway).
- [ ] Markdown renders; keyboard operable.
- [ ] All unit tests passing; coverage not regressed.
- [ ] Completion report with handoff for TC-A-02; TC-A-00 updated.
- [ ] Logger evidence included.

---

## 📖 Reference Documents

- V-Model Framework: `project_management/_templates/V_MODEL_FRAMEWORK.md`
- Architecture: `project_management/architecture/README.md`
- Epic: `project_management/epics/EPIC_002_CRAFTER_CHAT_UI.md`
- Component: `project_management/epics/EPIC_002/TC_A_CHAT_AND_FILES/TC-A-00_COMPONENT_DEFINITION.md`
- Predecessor Report: `project_management/epics/EPIC_001/TC_C_ACCESSIBILITY_REFS/TC-C-02_COMPLETION_REPORT.md`
- SW Requirements: SW-REQ-CHAT (see TC-A-00)

---

## 🔗 Related Issues

- Depends On: EPIC_001 TC-C-02 (gateway surface)
- Blocks: TC-A-02 (Toolcall view + closer)
- Related: TC-B streaming (attaches to this thread)

---

## Gate Results (filled during execution)

| Gate | Level | Result | Notes |
|------|-------|--------|-------|
| Pre-check test suite (Task 0.2) | SWE4 | ⬜ PENDING | |
| Post-implementation suite (Task 6) | SWE4 | ⬜ PENDING | |
| Coverage vs baseline | SWE4 | ⬜ PENDING | |
| Coverage vs target | ADVISORY | ⬜ PENDING | |
