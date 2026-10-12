# TC-B-01: SSE Streaming + Picture Input

**Component**: Stream + Settings
**Epic**: E-002 Crafter Chat UI
**V-Model**: SWE3-B-01
**Type**: 🔨 IMPLEMENTATION
**Priority**: P0-Critical
**Estimated Effort**: M
**Dependencies**: TC-A-02 (chat thread + toolcall view)
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

Stream agent replies incrementally into the thread with toolcall rendering, and let users send
pictures mid-chat. Without streaming the chat feels dead; without pictures users cannot point
at visual problems (story #3).

**High Stakes**: Broken streaming = unusable chat.
**Constraints**: SSE (not WebSocket); reduced-motion respect; image resize before send.

---

## 🏗️ Architectural Context

```
Scaico/LiteLLM → SSE → useChatStream → thread + ToolcallView
Composer → PictureInput → upload/resize → message attachment
```

See: `project_management/architecture/README.md` for full context.

---

## Traceability

| Level | ID | Artifact |
|-------|-----|---------|
| SYS1 | SYS1-002 | Epic: EPIC_002_CRAFTER_CHAT_UI.md |
| SWE1 | SWE1-B | TC: TC-B-00_COMPONENT_DEFINITION.md |
| SWE3 | SWE3-B-01 | This issue |
| SWE4 | — | Unit tests in: `view/src/.../*.test.tsx` |

---

## 📋 Task List

### 0.0 Read Architecture Documentation [MANDATORY]

- [ ] **Read: `project_management/architecture/README.md`**
- [ ] **Read: relevant diagrams** in `project_management/architecture/diagrams/`

### 0.1 Read Predecessor Context [MANDATORY]

- [ ] **Read: `TC-B-00_COMPONENT_DEFINITION.md`**
- [ ] **Read: `TC-A-02_COMPLETION_REPORT.md`** ← chat components handoff

### 0.2 Run Full Test Suite [MANDATORY GATE 🔴]

- [ ] Test runner + `tsc -b` + lint (MANDATORY from TC-X-02); baseline; Gate: 0 new issues.

### 0.3 Tooling Gate (TC-X-01 criterion)

- [ ] typecheck + tests + lint clean before handoff to TC-B-02.

### 1. Investigate Requirements

- [ ] Read: swaibian-one `scaico_client.py::send_task_stream` + epic 005 image pipeline
  (reference only).

### 1.5 Logging & Observability Integration [MANDATORY CROSS-CUTTING]

- [ ] Instrument stream lifecycle + image pipeline; never log prompts, content, image data, keys.

### 2. Write/Update Requirements

- [ ] Record streaming + picture contracts.

### 3. Investigate Architecture

- [ ] Review: SSE event shapes; image upload/resize/serving path.

### 4. Implement Code

- [ ] `useChatStream.ts`: SSE subscription, incremental render, toolcall events, error/retry,
  reduced-motion handling.
- [ ] `PictureInput.tsx`: picker/paste/drop image, resize client-side, attach to message.

### 5. Create Unit Tests (SWE4) [MANDATORY]

- [ ] Stream hook tests (mocked SSE): chunks, toolcalls, errors, retry; picture resize/attach;
  redaction tests.

### 6. Run Full Test Suite + Coverage [MANDATORY GATE 🔴]

- [ ] Runner + typecheck + lint 0 new errors; coverage not regressed.

### 7. Create Documentation

- [ ] Streaming + picture docs; note for closer.

### 8. Write Completion Report & Handoff [MANDATORY]

- [ ] Complete `TC-B-01_COMPLETION_REPORT.md`
- [ ] **Write handoff section for TC-B-02 team** — MUST include: what was built, decisions +
  deviations, limitations/edge cases, open risks, usage examples, gate results.
- [ ] Update `TC-B-00_COMPONENT_DEFINITION.md` with status + new decisions

---

## ⚠️ Constraints

- SSE only; no WebSocket.
- Images resized before send; no raw uploads in logs.

---

## 📁 Files to Modify

| Action | File Path | Description |
|--------|-----------|-------------|
| Create | `view/src/.../useChatStream.ts` | SSE streaming hook |
| Create | `view/src/.../PictureInput.tsx` | Image send |
| Create | `view/src/.../*.test.tsx` | Hook + component tests |

---

## ✅ Acceptance Criteria

- [ ] Incremental stream render with toolcalls (mocked SSE).
- [ ] Picture attach + resize works.
- [ ] All unit tests passing; coverage not regressed.
- [ ] Completion report with handoff for TC-B-02; TC-B-00 updated.
- [ ] Logger evidence included.

---

## 📖 Reference Documents

- V-Model Framework: `project_management/_templates/V_MODEL_FRAMEWORK.md`
- Architecture: `project_management/architecture/README.md`
- Epic: `project_management/epics/EPIC_002_CRAFTER_CHAT_UI.md`
- Component: `project_management/epics/EPIC_002/TC_B_STREAM_AND_SETTINGS/TC-B-00_COMPONENT_DEFINITION.md`
- Predecessor Report: `project_management/epics/EPIC_002/TC_A_CHAT_AND_FILES/TC-A-02_COMPLETION_REPORT.md`
- SW Requirements: SW-REQ-STREAM (see TC-B-00)

---

## 🔗 Related Issues

- Depends On: TC-A-02
- Blocks: TC-B-02 (Settings + closer)

---

## Gate Results (filled during execution)

| Gate | Level | Result | Notes |
|------|-------|--------|-------|
| Pre-check test suite (Task 0.2) | SWE4 | ⬜ PENDING | |
| Post-implementation suite (Task 6) | SWE4 | ⬜ PENDING | |
| Coverage vs baseline | SWE4 | ⬜ PENDING | |
| Coverage vs target | ADVISORY | ⬜ PENDING | |
