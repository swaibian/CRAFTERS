# TC-C-02: Teams E2E + Epic Closer — Completion Report

**Issue**: TC-C-02
**Component**: Package + Teams
**V-Model**: SWE3-C-02
**Type**: 🔨 IMPLEMENTATION
**Status**: ✅ Complete
**Completed**: 2026-10-12

---

## 1. What Was Built

### New Files

| File | Purpose | Serves |
|------|---------|--------|
| (none — wiring + tests) | Team select → agent runs bound to `team_id`; Scaico-key + gateway + active-profile server persistence | SW-REQ-PACK e2e |

### Changed Files

| File | Change |
|------|--------|
| `view/src/lib/api.ts` | Added `fetchSettingsActive`, `setActiveProfile` (`PUT /api/settings/active`), `saveScaicoKey`, `selectTeam`, `saveGatewayEndpoint` — selections now persist server-side, not just sessionStorage |
| `view/src/components/Settings.tsx` | Scaico key input + save; team select persists via `PUT /api/settings/team`; gateway saves server-side; active profile uses the real route; loads server state on mount |
| `view/src/components/Settings.test.tsx` | New test: team select + Scaico save + gateway save all hit the right routes (31 view tests total) |
| `controller/tests/test_service.py` | New `test_teams_e2e_select_then_chat` (team → chat SSE → fallback + direct assertions; 47 controller tests total) |
| `project_management/architecture/diagrams/component-overview.md` | Full-stack rows (controller + view + compose) |
| `project_management/architecture/diagrams/api-contracts.md` | Team + settings persistence contracts |
| `project_management/architecture/traceability/requirements-matrix.md` | SW-REQ-PACK row → ✅ |
| `project_management/architecture/traceability/coverage-map.md` | SW-REQ-PACK row → ✅ |
| `project_management/architecture/README.md` | Change log + Last updated by TC-C-02 |
| `project_management/epics/EPIC_002_CRAFTER_CHAT_UI.md` | TC rows → ✅, Status → ✅ Complete |
| `project_management/epics/EPIC_OVERVIEW.md` | E-002 row → ✅ Complete |

### APIs / Contracts Defined

| Module | API |
|--------|-----|
| Teams e2e | `PUT /api/settings/team {team_id}` → select; `POST /api/chat/stream {…, team_id}` → run bound to team; `GET /api/settings/active` → `{selected_team_id, scaico {mailto}, mock}` |
| Persistence | Active profile, Scaico key, team, gateway endpoint all survive reload (server store) |

---

## 2. Key Decisions

| Decision | Rationale |
|----------|-----------|
| View persists selections server-side (sessionStorage = cache only) | Selections must survive reload and drive the agent loop; local-only state was a real gap found by the e2e probe |
| `PUT` (not POST) for team/scaico/gateway/active | Idempotent selection updates; matches existing settings routes |
| Scaico key input added to the team section | Key + team select belong together (story #4); mailto CTA still shows when no teams |

### Gap analysis (TC-C-01 review — closer duty)

| # | Finding | Disposition |
|---|---------|-------------|
| 1 | View never persisted team/Scaico/gateway/active server-side (local state only) | **Fixed**: 5 api fns + Settings wiring + persistence test |
| 2 | `handleActivate` called `updateProfile(id, {active_profile_id})` (wrong route shape) | **Fixed**: dedicated `PUT /api/settings/active` |
| 3 | Probe used POST on a PUT route (405) | Probe fault, not app fault; corrected probe now passes |

---

## 3. Gate Results

| Gate | Result | Notes |
|------|--------|-------|
| Pre-check test suite (Task 0.2) | ✅ suites green | no regressions |
| Post-implementation suite (Task 6) | ✅ view 31 + controller 47 + gateway 158 passed | 0 failures |
| Coverage vs baseline | ✅ no regressions | persistence + e2e exercised |
| Typecheck | ✅ tsc + compileall clean | 🔴 MANDATORY — met |
| Lint | ✅ oxlint + ruff clean | 🔴 MANDATORY — met |
| TC-C integration (Task 8) | ✅ teams e2e (select → chat SSE → fallback + direct) | self-verify |
| SYS3 smoke (Task 8) | ✅ PASS: full native stack (`:8787/:8790/:8791`) + sheet/photo/pdf loops + settings + teams | below |

## 3.5 Logger Evidence (mandatory)

| Item | Evidence |
|------|----------|
| Team select + agent runs instrumented | `api.team.select`, agent loop events carry `team_id` where bound |
| Keys never logged | Scaico save logs `{}` only; `test_logging_redaction.py` + live `SECRET` absence |
| Audit/metrics separation | Controller logger names; metrics reserved |

---

## EPIC_002 Boundary Evidence

- All TCs ✅: TC-A (chat+files+toolcalls) + TC-B (stream+settings) + TC-C (package+teams).
- `EPIC_002_CRAFTER_CHAT_UI.md`: TC table ✅, Status ✅ Complete, Last Updated 2026-10-12.
- `EPIC_OVERVIEW.md`: E-002 → ✅ Complete (E-001 ✅ already).
- `architecture/README.md`: change log + Last updated by TC-C-02.
- Final full suites: gateway 158 + controller 47 + view 31 = **236 tests, 0 failures**.

---

## Self-verification (no-reviews mode)

| Gate | Command | Exit | Result |
|------|---------|------|--------|
| D1 Lint | `npm run lint` + `ruff check/format` (gateway+controller) | 0 | clean |
| D2 Typecheck/build | `npm run build` + `compileall` (gateway+controller) | 0 | clean |
| D3 Tests | view 31 + controller 47 + gateway 158 | 0 | 236 passed, 0 failed |
| D4 Smoke | native 3-service stack: sheet C3=99/B2=7, photo 800px, pdf 90°, SSE order exact, settings masked, teams e2e | 0 | NORTH STAR PASS |
| D5 Self-checklist | every file → SW-REQ-PACK; impl + test; keys masked/never in repo (verified); all issue boxes ticked | — | yes to all |

Wiring chain proof: `#/settings` → profile/team/gateway persist via `PUT /api/settings/*` → `#/` picker → dropzone → `POST /api/files/open` → header → composer → `POST /api/chat/stream` (SSE) → agent loop (adapters + ledger) → `response.completed {records}` → download route returns edited bytes.

## Lane 5 audit (2026-10-12) — executed evidence

- Re-ran full suites: gateway **188** (+9 skipped = real-CLI tests, no binaries) + controller **77** + view **72** = **337 passed, 0 failed** (report claimed 236 = 158+47+31; counts grew since writing — superseded).
- Live native stack observed: `:8790/api/health` → `{"ok":true}`, `:8791` → 200, `:8787/mcp` → HTTP 400 (up, needs session init).
- Final demo script produced: `docs/DEMO.md` (4-step northstar: compose/start → PhotoCraft → snapshot/render/assert/record → Pdf/Grid → bridge live GUI).
- Verdict: KEEP ✅ Complete — teams e2e test green, demo path documented. Residual TODOs unchanged (user key, real CLIs, upstream drafts).

Residual risks: real LLM needs a user key (setup ready, mock until then); real Craft CLIs unwired (no toolchain/binaries — adapters bridge local docs; gateway real-CLI path takes over when present); upstream PRs are drafts.

Independent review intentionally omitted — TC-C is declared `no-reviews`; gap analysis is inherited by the TC closer (TC-C-02, this issue).
