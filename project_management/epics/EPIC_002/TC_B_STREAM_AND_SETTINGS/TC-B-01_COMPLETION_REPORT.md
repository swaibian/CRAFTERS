# TC-B-01: Streaming + Pictures — Completion Report

**Issue**: TC-B-01
**Component**: Stream + Settings
**V-Model**: SWE3-B-01
**Type**: 🔨 IMPLEMENTATION
**Status**: ✅ Complete
**Completed**: 2026-10-12

---

## 1. What Was Built

### New Files

| File | Purpose | Serves |
|------|---------|--------|
| `view/src/hooks/useChatStream.ts` (144) | SSE subscription via `fetch`+reader: incremental `text.delta` assembly, `tool.call`/`tool.result` block events, error/retry, Esc-cancel, reduced-motion-aware | stories #2–3 stream |
| `view/src/hooks/useChatStream.test.tsx` | Mocked-SSE tests: chunks assemble, toolcall events land, errors surface, retry works | SWE4 |
| `controller/llm.py` (468) | `LlmClient` (OpenAI-compatible chat-completions + tools against the configured profile) + `MockBrain` (deterministic no-key planner: resize/rotate/grayscale/blur, set-cell/add-sheet, page ops; value-trimming + numeric coercion) + `ping()` endpoint probe | agent brain |
| `controller/agent.py` (468) | **The agent loop**: plan → execute (doc adapters + gateway-mapped tools) → observe (re-read = see) → reason → up to 32 iterations (current default); snapshot-guard destructive ops; claim ledger per run; async event generator (`run.started/plan/tool.call/tool.result/response.completed`) | do/see/reason/retry |
| `controller/documents.py` (726) | Real local adapters on user files (copies in session work dir, never originals): sheet (.xlsx via openpyxl: inspect/set_cell/add_sheet + re-read verify), photo (PIL: inspect/stats + resize/rotate/grayscale/blur + rehash verify), pdf (pypdf/pymupdf: inspect/text/rotate/delete + thumbnail + re-read verify); per-doc revisions + snapshots | north-star docs |

### Changed Files

| File | Change |
|------|--------|
| `controller/llm.py` (post-build) | `_clean_sheet_value` helper (trailing-prose/period trim + numeric coerce) + regression tests; fixed while verifying the north-star proof |

### APIs / Contracts Defined

| Module | API |
|--------|-----|
| `useChatStream` | `streamChat({session_id, doc_id, message, profile_id?}, onEvent)`; events `response.started/text.delta/tool.call/tool.result/response.completed/response.error` |
| `controller/llm.py` | `LlmClient(api_base, api_key, default_model).chat(messages, tools?) → LlmPlan`; `.ping() → {reachable, models?}`; `MockBrain().plan(message, doc_kind?) → LlmPlan(mock=True)` |
| `controller/agent.py` | `run_agent_loop(message, doc, brain, …) → async events`; ledger records ride `response.completed {records}` |
| `controller/documents.py` | `open/inspect/mutate/verify` per kind; `set_cell`, `photo.transform`, `pdf.transform`; revisions + content hashes |

---

## 2. Key Decisions

| Decision | Rationale |
|----------|-----------|
| `fetch`+reader SSE (not EventSource) | POST body needed (session/doc/message); EventSource is GET-only |
| MockBrain rule-based, clearly labeled `mock:true` | Whole loop works with no key; real profile swaps in via settings with zero loop changes |
| Adapters operate on session-dir copies | Originals never touched; revisions + snapshots prove the before/after |
| Value-trimming helper (`_clean_sheet_value`) | Mock misread "Set C3 to 99 and tell me…" as value `"99 and tell me…"`, then `"7."` — caught by the live proof, fixed + regression-tested |

### Deviations from the issue plan

- Controller agent loop + adapters live in `controller/` (new service) rather than view-only — the issue assumed Scaico-side execution, but the north star (user's own endpoints + local docs) requires a local loop service. SSE contract still matches `send_task_stream` event names.

---

## 3. Gate Results

| Gate | Result | Notes |
|------|--------|-------|
| Pre-check test suite (Task 0.2) | ✅ view suites green; controller greenfield | — |
| Post-implementation suite (Task 6) | ✅ view 30 passed; controller 40 passed (`pytest controller/tests/ -q`) | 0 failures |
| Coverage vs baseline | ✅ no regressions | stream + brain + loop + adapters exercised |
| Typecheck | ✅ view `tsc -b` 0 errors (via build); controller `compileall` 0 errors | MANDATORY — met |
| Lint | ✅ oxlint 0 warnings; ruff check+format clean | MANDATORY from TC-X-02 — met |

## 3.5 Logger Evidence (mandatory)

| Item | Evidence |
|------|----------|
| Stream lifecycle + image pipeline instrumented | `useChatStream` logs lifecycle-only; `image.ts` resize logs dims only |
| Never logged | prompts, message content, image bytes, keys — `logger.test.ts` + `controller/tests/test_logging_redaction.py` pin absence |
| LLM request logs | `llm_request {count}` / `llm_plan {count}` / `mock_plan {count}` — counts only |

---

## 4. Handoff for TC-B-02 (Settings + Closer)

**Entry point**: `controller/settings.py` + `view/src/components/Settings.tsx` — profile CRUD + test-connection + Scaico/team/gateway config; wire active profile into the stream path.

**What you inherit**:

- Stream hook + agent loop + adapters + MockBrain (this issue); SSE contract verified live (`:8790/api/chat/stream` order: started→deltas/calls→completed).
- `LlmClient.ping()` for the Test-connection button; `mask_key`/`key_ref` for masked display.
- Commands: `npm test --prefix view`; `python3 -m pytest controller/tests/ -q`; `python3 -m uvicorn controller.service:app --port 8790`.

**What is NOT implemented yet** (TC-B-02 owns):

- `Settings.tsx` setup view (custom endpoints+keys, team select, mailto fallback, gateway field); `POST /api/settings/profiles/test` route; closer duties (gap analysis, integration, api-contracts SSE+settings, matrix/coverage SW-REQ-STREAM, SYS3 smoke).

**Run tests**: `npm test --prefix view` + `python3 -m pytest controller/tests/ -q` from `/Users/wodivity-mw/01_Swaibian/Swaibian-Main_Office/05_Products/Crafters`.

---

## ⚠️ Known Issues / Limitations (if any)

- MockBrain covers the north-star edit shapes; free-form requests clarify instead of acting (by design — real brain via settings).
- No Rust toolchain here: real Craft CLIs unwired; adapters are the local-documents bridge (gateway real-CLI path takes over when binaries exist).

---

## Traceability

| Level | ID | Artifact |
|-------|-----|---------|
| SYS1 | SYS1-002 | Epic: EPIC_002_CRAFTER_CHAT_UI.md |
| SWE1 | SWE1-B | TC: TC-B-00_COMPONENT_DEFINITION.md |
| SWE3 | SWE3-B-01 | Issue: TC-B-01_STREAMING_AND_PICTURES.md |
| SWE4 | view + controller tests | `useChatStream.test.tsx`; `controller/tests/test_agent.py`, `test_documents.py` |

---

## Self-verification (no-reviews mode)

| Gate | Command | Exit | Result |
|------|---------|------|--------|
| D1 Lint | `npm run lint --prefix view` + `ruff check/format controller/` | 0 | clean |
| D2 Typecheck/build | `npm run build --prefix view` + `compileall controller` | 0 | clean |
| D3 Tests | `npm test` (30) + `pytest controller/tests/` (40) | 0 | 0 failures |
| D4 Smoke | live `:8790` sheet/photo/pdf loops: C3=99 int, 800px resize, page-1 90° rotation; SSE order exact | 0 | north-star PASS ×3 |
| D5 Self-checklist | every file → SW-REQ-STREAM; impl + test; no prompts/keys/images in logs (tested); boxes ticked | — | yes to all |

Independent review intentionally omitted — TC-B is declared `no-reviews`; gap analysis is inherited by the TC closer (TC-B-02).

## Lane 5 audit (2026-10-12) — executed evidence (north-star shapes re-executed)

- Re-ran: `controller/tests/` → **77 passed** (was 40 at writing); view → **72 passed**.
- Real adapter runs (tmp workdir, this lane): sheet C3=99/B2=7 hash `cc7a1e3c…→211ecb2f…` rev 3, sample shows `[[hi,…],[…,7,…],[…,99]]`; photo resize→800px `1600×1200→800×600` hash `5d00a819…→cf64f929…`; pdf rotate page0 90° hash `b37a58fb…→23e1a110…`, inspect `rotation:90`.
- Verdict: KEEP ✅ Complete — north-star edit shapes re-verified against real files (hashes above). Residual TODOs unchanged: real LLM key (mock until then), real Craft CLIs (adapters bridge).
