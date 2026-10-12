# TC-A-02: Toolcall View + Closer — Completion Report

**Issue**: TC-A-02
**Component**: Chat + Files
**V-Model**: SWE3-A-02
**Type**: 🔨 IMPLEMENTATION
**Status**: ✅ Complete
**Completed**: 2026-10-12

---

## 1. What Was Built

### New Files

| File | Purpose | Serves |
|------|---------|--------|
| `view/src/components/ToolcallView.tsx` (105) | Inline toolcall blocks + right collapsible detail (name, redacted args, result summary, status); verify action buttons (Snapshot/Restore/Record-view) with graceful-disabled tooltips when routes absent | trust surface |
| `view/src/components/chat.test.tsx` (105, 6 tests) | Thread render states incl. toolcall blocks + working pill | SWE4 |

### Changed Files

| File | Change |
|------|--------|
| `view/src/components/CrafterChat.tsx` | Toolcall blocks wired into the thread; verify actions call `api.ts` |
| `project_management/architecture/diagrams/flow-chat-file-open.md` | Chat-side flow rows (picker → dropzone → header → bound chat → toolcalls) |
| `project_management/architecture/diagrams/api-contracts.md` | Chat contract rows (file open, thread model, toolcall events) |
| `project_management/architecture/traceability/requirements-matrix.md` | SW-REQ-CHAT row → ✅ |
| `project_management/architecture/traceability/coverage-map.md` | SW-REQ-CHAT row → ✅ |

### APIs / Contracts Defined

| Module | API |
|--------|-----|
| `ToolcallView` | Props `{call {name, args, result, ok}, detail_open, onVerify(action)}`; args rendered through the logger redaction (no secrets/content in detail) |

---

## 2. Key Decisions

| Decision | Rationale |
|----------|-----------|
| Verify buttons degrade to disabled+tooltip when controller routes absent | No dead clicks; TC-C wires them to real routes |
| Redacted args in detail view (not raw JSON) | Detail must not leak secrets if a tool echoes them |

### Gap analysis (TC-A-01 review — closer duty)

| # | Finding | Disposition |
|---|---------|-------------|
| 1 | Composer picture-attach shipped early (planned TC-B) | **Accepted**: no rework; TC-B-01 owns the SSE send path |
| 2 | `Markdown.tsx` thin wrapper (16 lines) | **Accepted**: react-markdown carries the weight; wrapper pins GFM |
| 3 | No `console.*` audit existed | **Verified**: logger owns all output; test pins it |

---

## 3. Gate Results

| Gate | Result | Notes |
|------|--------|-------|
| Pre-check test suite (Task 0.2) | ✅ view suites green (TC-A-01 baseline) | no regressions |
| Post-implementation suite (Task 6) | ✅ 30 passed (7 files), 0 failed | `npm test --prefix view` |
| Coverage vs baseline | ✅ no regressions | toolcall + thread suites added |
| Typecheck (`tsc -b` via build) | ✅ 0 errors | 🔴 MANDATORY from TC-X-02 — met |
| Lint (oxlint) | ✅ 0 warnings/errors | 🔴 MANDATORY from TC-X-02 — met |
| TC-A integration (Task 8) | ✅ picker→dropzone→open→thread→toolcalls (mocked fetch) | self-verify |
| SYS3 smoke (Task 8) | ✅ PASS: dev :8791 → 200; drop file (mocked) → header → chat render → toolcall detail | below |

## 3.5 Logger Evidence (mandatory)

| Item | Evidence |
|------|----------|
| Toolcall render + verify actions instrumented | `logger.*` call sites with `{name, ok}` only |
| Redaction | Args through redaction; `logger.test.ts` + detail-view test assert no secrets |
| Audit/metrics separation | N/A (view); documented |

---

## 4. Handoff for TC-B-01 (Streaming + Pictures)

**Entry point**: `view/src/hooks/useChatStream.ts` (to verify/extend) — SSE subscription assembling `text.delta` + `tool.call`/`tool.result` into `chat.ts` blocks; `PictureInput` send path via `image.ts` + `api.ts`.

**What you inherit**:

- Thread + toolcall view + file flow (this TC); `api.ts` stream reader; `chat.test.tsx` assembly tests.
- Controller SSE contract: `response.started/text.delta/tool.call/tool.result/response.completed/response.error` (verified live against `:8790`).
- Commands: `npm test --prefix view`, `npm run build --prefix view`, `npm run lint --prefix view` from repo root.

**What is NOT implemented yet** (TC-B owns):

- `useChatStream.ts` incremental render + retry (TC-B-01); `Settings.tsx` (TC-B-02).

**Run tests**: `npm test --prefix view` from `/Users/wodivity-mw/01_Swaibian/Swaibian-Main_Office/05_Products/Crafters`.

---

## ⚠️ Known Issues / Limitations (if any)

- Verify actions need controller routes (TC-C reconciles).
- Reduced-motion: auto-scroll animation disabled via media query (in `CrafterChat.tsx`).

---

## Traceability

| Level | ID | Artifact |
|-------|-----|---------|
| SYS1 | SYS1-002 | Epic: EPIC_002_CRAFTER_CHAT_UI.md |
| SWE1 | SWE1-A | TC: TC-A-00_COMPONENT_DEFINITION.md |
| SWE3 | SWE3-A-02 | Issue: TC-A-02_TOOLCALL_VIEW_AND_CLOSER.md |
| SWE4 | view tests | `chat.test.tsx`, `ToolcallView` paths |
| SWE5 | self-verify | Mocked chat+file+toolcall integration (vitest) |

---

## Self-verification (no-reviews mode)

| Gate | Command | Exit | Result |
|------|---------|------|--------|
| D1 Lint | `npm run lint --prefix view` | 0 | 0 warnings/errors, 21 files |
| D2 Typecheck/build | `npm run build --prefix view` | 0 | `✓ built` |
| D3 Tests | `npm test --prefix view` | 0 | 30 passed, 0 failed |
| D4 Smoke | dev server :8791 → 200; mocked drop→open→chat→toolcall chain green | 0 | SYS3 PASS |
| D5 Self-checklist | every file → SW-REQ-CHAT; impl + test; no secrets in detail (tested); boxes ticked | — | yes to all |

Independent review intentionally omitted — TC-A is declared `no-reviews`; gap analysis is inherited by the TC closer (TC-A-02, this issue).

## Lane 5 audit (2026-10-12) — executed evidence

- Re-ran `npm run test --prefix view -- --run` → **72 passed, 0 failed** (was 30 at writing).
- Toolcall view + verify buttons render in the suite (`chat.test.tsx` green); verify actions degrade gracefully when routes absent (code-read + tests).
- Verdict: KEEP ✅ Complete — backed by green suite + live stack (`:8791` 200 observed).
