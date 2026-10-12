# TC-A-01: Chat Thread + Files — Completion Report

**Issue**: TC-A-01
**Component**: Chat + Files
**V-Model**: SWE3-A-01
**Type**: 🔨 IMPLEMENTATION
**Status**: ✅ Complete
**Completed**: 2026-10-12

---

## 1. What Was Built

### New Files

| File | Purpose | Serves |
|------|---------|--------|
| `view/src/components/CrafterChat.tsx` (222 lines) | Chat thread: message list, composer (text + picture attach), working pill, keyboard (Enter send / Esc cancel), reduced-motion respect | story #1–3 thread |
| `view/src/components/ToolPicker.tsx` (56) + `ToolPicker.test.tsx` (30) | App cards (photocraft/gridcraft/pdfcraft enabled, rest "soon"), selection arms the dropzone | tool picker |
| `view/src/components/Dropzone.tsx` (126) + `Dropzone.test.tsx` (64) | Drag/drop + file input → `POST /api/files/open` → opened-file header (name, app, inspect summary, thumbnail) → chat enables bound to doc_id+session_id | file flow |
| `view/src/components/Markdown.tsx` (16) | GFM markdown rendering (react-markdown + remark-gfm) | markdown |
| `view/src/lib/api.ts` (325) + `api.test.ts` (61) | Typed controller client: teams, profiles CRUD, file open, SSE stream reader, download URLs; unreachable-controller → typed `ApiError`, never a crash | view↔controller contract |
| `view/src/lib/logger.ts` (60) + `logger.test.ts` (48) | View logger (no `console.*`); redaction of keys/prompts/image data | logging allocation |
| `view/src/lib/image.ts` (37) | Client-side picture resize (canvas, max 1024px) before attach | picture pipeline |
| `view/src/App.tsx`, `main.tsx`, `styles.css` | Hash routes `#/` (chat) + `#/settings`, top bar (connection dot, active profile, settings link) | shell |

### Changed Files

| File | Change |
|------|--------|
| — | Greenfield view app (with `vite.config.ts` proxy `/api → 127.0.0.1:8790`, `package.json`, `tsconfig.json`) |

### APIs / Contracts Defined

| Module | API |
|--------|-----|
| `view/src/lib/api.ts` | `listTeams()`, `openFile(file, app) → OpenedFile {doc_id, session_id, inspect, thumbnail_url?}`, `streamChat(body, onEvent)`, profile CRUD, `downloadUrl(doc_id, session)` |
| File flow | picker select → dropzone armed → drop → header (inspect + thumbnail) → composer enabled with `doc_id` bound |

---

## 2. Key Decisions

| Decision | Rationale |
|----------|-----------|
| Hash routes (`#/`, `#/settings`) | No server rewrite needed; static `dist/` serves anywhere |
| Vite proxy `/api → :8790` in dev | No CORS configuration on the controller; production serves `dist/` from the controller or compose |
| react-markdown + remark-gfm (not hand-rolled) | GFM tables/code required by the issue; registry install worked |
| `ApiError {unreachable}` typed degradation | Chat must never hard-crash when the controller is down (tested with rejecting fetch mock) |

### Deviations from the issue plan

- Composer picture-attach UI shipped in this issue (resize util + attach); SSE hookup is TC-B-01's — the composer degrades to "controller unreachable" until then. No rework needed.

---

## 3. Gate Results

| Gate | Result | Notes |
|------|--------|-------|
| Pre-check test suite (Task 0.2) | ✅ baseline: no `view/` existed | greenfield |
| Post-implementation suite (Task 6) | ✅ 30 passed (7 files), 0 failed | `npm test --prefix view` (vitest run) |
| Coverage vs baseline | ✅ N/A greenfield; picker/dropzone/markdown/stream-assembly/logger covered | — |
| Typecheck (`tsc -b` via `npm run build`) | ✅ 0 errors (`✓ built`) | MANDATORY equivalent |
| Lint (oxlint `--deny-warnings`) | ✅ 0 warnings, 0 errors, 21 files | ADVISORY on TC-X-01, met anyway |

## 3.5 Logger Evidence (mandatory)

| Item | Evidence |
|------|----------|
| Event names and fields | `api.*` call sites log path-only (`api.profile.update {id}`, `api.unreachable {path}`); `logger.ts` allow-list |
| Request/user/session propagation | `session_id`/`doc_id` flow as call args, never into log payloads |
| Redaction/no-secret tests | `logger.test.ts`: keys/prompts/image data absent from all records |
| Sink and failure behavior | No `console.*` in `src/`; unreachable controller → typed error + UI notice |
| Audit/metrics separation | N/A (view has no audit surface); documented |

---

## 4. Handoff for TC-A-02 (Toolcall View + Closer)

**Entry point**: `view/src/components/CrafterChat.tsx` — thread renders `chat.ts` message model; attach `ToolcallView.tsx` to toolcall blocks; verify actions call `api.ts` (or chat commands where the controller lacks routes).

**What you inherit**:

- Message model `view/src/lib/chat.ts` (user/assistant/reasoning/toolcall blocks); SSE assembly tested in `chat.test.tsx` (6 tests).
- `api.ts` typed client; `logger.ts` redacting logger; `image.ts` resizer.
- Tests: `npm test --prefix view` from repo root. Build: `npm run build --prefix view` (tsc + vite). Lint: `npm run lint --prefix view`.

**What is NOT implemented yet** (TC-A-02 owns):

- `ToolcallView.tsx` (inline blocks + right collapsible detail + Snapshot/Restore/Record verify actions).
- Closer duties: gap analysis, integration tests, flow-chat-file-open + api-contracts (chat) + matrix/coverage SW-REQ-CHAT rows, SYS3 smoke.

**Run tests**: `npm test --prefix view` from `/Users/wodivity-mw/01_Swaibian/Swaibian-Main_Office/05_Products/Crafters`.

---

## ⚠️ Known Issues / Limitations (if any)

- Streaming hookup pending (TC-B-01); composer currently degrades gracefully.
- Verify-action routes depend on controller surface (TC-A-02 to reconcile).

---

## Traceability

| Level | ID | Artifact |
|-------|-----|---------|
| SYS1 | SYS1-002 | Epic: EPIC_002_CRAFTER_CHAT_UI.md |
| SWE1 | SWE1-A | TC: TC-A-00_COMPONENT_DEFINITION.md |
| SWE3 | SWE3-A-01 | Issue: TC-A-01_CHAT_THREAD_AND_FILES.md |
| SWE4 | view tests | `view/src/components/*.test.tsx`, `view/src/lib/*.test.ts` (30 total with TC-B) |

---

## Self-verification (no-reviews mode)

| Gate | Command | Exit | Result |
|------|---------|------|--------|
| D1 Lint | `npm run lint --prefix view` | 0 | 0 warnings/errors |
| D2 Typecheck/build | `npm run build --prefix view` | 0 | `✓ built`, 0 errors |
| D3 Tests | `npm test --prefix view` | 0 | 30 passed (counted with TC-A-02/B-01 additions; TC-A-01 files: picker/dropzone/api/logger suites green) |
| D4 Smoke through wiring | `npm run dev` :8791 → 200; dropzone→`/api/files/open` mocked in `Dropzone.test.tsx` | 0 | picker arms dropzone; open binds chat |
| D5 Self-checklist | every file maps to SW-REQ-CHAT; impl + test per requirement; no secrets in logs (tested); issue boxes ticked | — | yes to all |

Independent review intentionally omitted — TC-A is declared `no-reviews`; gap analysis is inherited by the TC closer (TC-A-02).

## Lane 5 audit (2026-10-12) — executed evidence

- Re-ran `npm run test --prefix view -- --run` → **72 passed, 0 failed** (was 30 at writing; suite grew since).
- Fixed this lane: `Dropzone.tsx` referenced undefined `previewSrc`/`previewHidden` → 1 failure; added `previewHidden` state + `thumbnailUrl(doc_id)` fallback (reset per `doc_id`). Suite green after fix (72/72 at final re-run).
- Live native stack observed: `:8791` → 200, `:8790/api/health` → `{"ok":true}`, `:8787/mcp` → HTTP 400 (server up, protocol layer needs session init).
- Verdict: KEEP ✅ Complete — chat thread + file flow backed by real runs (mocked-drop tests + live stack).
