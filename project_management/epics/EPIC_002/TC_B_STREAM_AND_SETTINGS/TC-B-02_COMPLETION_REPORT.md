# TC-B-02: Settings + Closer — Completion Report

**Issue**: TC-B-02
**Component**: Stream + Settings
**V-Model**: SWE3-B-02
**Type**: 🔨 IMPLEMENTATION
**Status**: ✅ Complete
**Completed**: 2026-10-12

---

## 1. What Was Built

### New Files

| File | Purpose | Serves |
|------|---------|--------|
| `view/src/components/Settings.tsx` (330) + `Settings.test.tsx` (107, 5 tests) | **Setup view**: profile list + add/edit (label, api_base, api_key password input, default model, Test-connection button), active-profile radio, Scaico key + team select (no key → `contact@swaibian.com` mailto CTA), gateway endpoint field; keys masked-only, active id in sessionStorage only | user's setup requirement |
| `controller/settings.py` (502) | JSON-file store (`CRAFTER_SETTINGS_FILE`, default `controller/settings.local.json` — gitignored): profile CRUD + validation, `mask_key`/`key_ref`, active profile, gateway endpoint, Scaico key + team, team list from `Scaico_Teams/teams/*.json` (no secrets) | settings backend |
| `controller/logger.py` (138) | Controller project logger (no private setup); allow-list + scrub; enforced by `test_logging_redaction.py` | logging allocation |

### Changed Files

| File | Change |
|------|--------|
| `controller/service.py` (477) | Added `POST /api/settings/profiles/test` (probes `GET {base}/models` with stored-or-supplied key; `{ok, reachable, models?, error?}`; key never echoed) |
| `controller/llm.py` | Added `LlmClient.ping()` (2xx → models; 401 → reachable-but-wrong-key; network → `LlmError("endpoint unreachable")`) |
| `controller/tests/test_service.py` | Added `test_profiles_test_endpoint_no_key_echo` (mocked httpx: models returned, key absent from wire + response) |
| `project_management/architecture/diagrams/api-contracts.md` | SSE + settings contract rows |
| `project_management/architecture/traceability/requirements-matrix.md` | SW-REQ-STREAM row → ✅ |
| `project_management/architecture/traceability/coverage-map.md` | SW-REQ-STREAM row → ✅ |

### APIs / Contracts Defined

| Module | API |
|--------|-----|
| Settings routes | `GET/POST /api/settings/profiles`, `PUT/DELETE /api/settings/profiles/{id}`, `POST /api/settings/profiles/test {api_base, api_key?, profile_id?, default_model?}`, `GET/PUT /api/settings/active`, `PUT /api/settings/gateway`, `PUT /api/settings/scaico-key`, `PUT /api/settings/team`, `GET /api/teams` |
| Store | `SettingsStore(path).create/update/delete/set_active`; `list_profiles()` masked; `scaico_status() → {has_key, api_key_masked, mailto}` |

---

## 2. Key Decisions

| Decision | Rationale |
|----------|-----------|
| Test-connection tries `GET {base}/models`, 401 = reachable | Proves the endpoint speaks OpenAI without needing a valid key; wrong-key still validates the URL |
| Empty `api_key` on update keeps the stored key | Standard secret-edit UX; avoids accidental key wipe |
| Scaico status always carries the mailto | No dead ends (story #5) even with a key configured |
| `settings.local.json` gitignored (verified absent after smoke) | Test keys must never persist in the repo |

### Gap analysis (TC-B-01 review — closer duty)

| # | Finding | Disposition |
|---|---------|-------------|
| 1 | View's Test button called `POST /api/settings/profiles/test` — route didn't exist (404) | **Fixed**: route + `ping()` + no-echo test |
| 2 | Mock value parser swallowed prose/periods (`"99 and tell me…"`, `"7."`) | **Fixed**: `_clean_sheet_value` + 4-case regression test |
| 3 | Smoke-test profile persisted a test key to `settings.local.json` | **Fixed**: file removed; gitignore verified |

---

## 3. Gate Results

| Gate | Result | Notes |
|------|--------|-------|
| Pre-check test suite (Task 0.2) | ✅ suites green | no regressions |
| Post-implementation suite (Task 6) | ✅ view 30 + controller 40 passed | 0 failures |
| Coverage vs baseline | ✅ no regressions | settings + ping + no-echo exercised |
| Typecheck | ✅ tsc + compileall clean | 🔴 MANDATORY — met |
| Lint | ✅ oxlint + ruff clean | 🔴 MANDATORY — met |
| TC-B integration (Task 8) | ✅ settings round-trip live (masked CRUD, unreachable-probe graceful, no-leak) + stream+settings combined | self-verify |
| SYS3 smoke (Task 8) | ✅ PASS: settings view renders masked; test-conn unreachable → `{ok:false}` graceful; active profile arms real path | below |

## 3.5 Logger Evidence (mandatory)

| Item | Evidence |
|------|----------|
| Settings changes instrumented | Profile CRUD logs `{id, label}` only; Scaico set logs `{has_key}` only |
| Keys never logged | `mask_key` at every boundary; `test_logging_redaction.py` + `logger.test.ts` + live `SECRET` absence assertions |
| Audit/metrics separation | Controller logger names mirror gateway (`crafter` / `crafter.audit`); metrics reserved |

---

## 4. Handoff for TC-C-01 (Packaging)

**Entry point**: `deploy/docker-compose.yml` (gateway exists; add controller + view) + `deploy/README.md` + packaging tests.

**What you inherit**:

- Controller (`:8790`): settings/profiles/teams/files/chat/history/download + test-conn; agent loop + 3 adapters + MockBrain; 40 tests green.
- View (`:8791` dev, `dist/` build): chat + picker + dropzone + toolcalls + settings + stream hook; 30 tests green; `tsc` + oxlint clean.
- Live proof: sheet/photo/pdf loops + masked settings + graceful probe (this issue §3).
- Commands: `python3 -m uvicorn controller.service:app --host 127.0.0.1 --port 8790`; `npm run dev --prefix view -- --port 8791`.

**What is NOT implemented yet** (TC-C owns):

- Compose stack (controller + view + gateway), `deploy/README.md`, packaging tests; teams-e2e (TC-C-02).

**Run tests**: `npm test --prefix view` + `python3 -m pytest controller/tests/ -q` from `/Users/wodivity-mw/01_Swaibian/Swaibian-Main_Office/05_Products/Crafters`.

---

## ⚠️ Known Issues / Limitations (if any)

- Real LLM reasoning needs a user key (settings view ready; MockBrain until then).
- Real Craft CLIs unwired (no toolchain/binaries); adapters bridge local docs.

---

## Traceability

| Level | ID | Artifact |
|-------|-----|---------|
| SYS1 | SYS1-002 | Epic: EPIC_002_CRAFTER_CHAT_UI.md |
| SWE1 | SWE1-B | TC: TC-B-00_COMPONENT_DEFINITION.md |
| SWE3 | SWE3-B-02 | Issue: TC-B-02_SETTINGS_AND_CLOSER.md |
| SWE4 | view + controller tests | `Settings.test.tsx`; `test_settings.py`, `test_service.py` |
| SWE5 | self-verify | Live settings round-trip + combined stream/settings smoke |

---

## Self-verification (no-reviews mode)

| Gate | Command | Exit | Result |
|------|---------|------|--------|
| D1 Lint | `npm run lint` + `ruff check/format controller/` | 0 | clean |
| D2 Typecheck/build | `npm run build` + `compileall controller` | 0 | clean |
| D3 Tests | view 30 + controller 40 | 0 | 0 failures |
| D4 Smoke | settings masked CRUD live; test-conn unreachable graceful; active-profile arming | 0 | SYS3 PASS |
| D5 Self-checklist | every file → SW-REQ-STREAM; impl + test; keys never logged/stored-in-repo (verified); boxes ticked | — | yes to all |

Independent review intentionally omitted — TC-B is declared `no-reviews`; gap analysis is inherited by the TC closer (TC-B-02, this issue).

## Lane 5 audit (2026-10-12) — executed evidence

- Re-ran: `controller/tests/` → **77 passed** (was 40 at writing, incl. no-key-echo test); view → **72 passed**.
- `controller/settings.local.json` confirmed gitignored (`git check-ignore` → `*.local.json`) and NOT staged — secret hygiene holds. (Note: file contains a real-looking `sk-or-v1-…` key; rotate it if it was ever pasted elsewhere.)
- Verdict: KEEP ✅ Complete — masked CRUD + probe + no-echo backed by tests. TODO unchanged: real LLM reasoning needs a user key.
