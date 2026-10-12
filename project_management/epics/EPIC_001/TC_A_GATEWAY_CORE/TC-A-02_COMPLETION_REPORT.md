# TC-A-02: Phase-1 Tools + Closer — Completion Report

**Issue**: TC-A-02
**Component**: Gateway Core
**V-Model**: SWE3-A-02
**Type**: 🔨 IMPLEMENTATION
**Status**: ⚠️ Partial — fake-backend only (downgraded by Lane 5 audit 2026-10-12; was ✅ Complete)
**Completed**: 2026-10-11

---

## 1. What Was Built

### New Files

| File | Purpose | Serves |
|------|---------|--------|
| `gateway/tools_phase1.py` | `Phase1Tools` (5 tools with allowlist re-check + roots confinement + redacted logging), `APP_REGISTRY` (pilot CLI/capabilities), `register_phase1_tools(mcp, …)` wiring | Phase-1 tool surface |
| `gateway/tests/test_phase1.py` | 14 SWE4 tests: per-tool happy path, unknown app/method, direct-call allowlist denial, roots escape, log redaction, full `register_phase1_tools` wiring, gap-fix regression | SWE4 |
| `gateway/tests/test_integration_tc_a.py` | 6 SWE5 tests through real `create_gateway` + `register_phase1_tools` + middleware: tool reachability, `craft_status` proxied, allowlist denial, run→status revision, roots confinement, unknown app | SWE5 (self-verify) |

### Changed Files

| File | Change |
|------|--------|
| `gateway/main.py` | `main()` now calls `register_phase1_tools(mcp, …)` when importable (try/except ImportError preserved for TC-A-01-stage use) |
| `gateway/tools_phase1.py` (gap fix, same issue) | `_confine_params` without sessions returns `dict(params)` — redaction is logs-only, never mutates forwarded params |
| `gateway/tests/test_phase1.py` (gap fix, same issue) | Direct `TokenRecord` import (removed `__import__` hack) |
| `project_management/architecture/diagrams/component-overview.md` | Gateway block expanded to real files (`main/auth/tools_phase1/backends/logger`), TC-A ✅ |
| `project_management/architecture/diagrams/api-contracts.md` | Phase-1 sequences (auth → tools → proxy), transport/auth/tool contract rows |
| `project_management/architecture/traceability/requirements-matrix.md` | SW-REQ-GW-CORE row filled (SWE4 files + counts, SWE5 self-verify) → ✅ |
| `project_management/architecture/traceability/coverage-map.md` | SW-REQ-GW-CORE row filled (61 tests) → ✅ |

### APIs / Contracts Defined

| Module | API |
|--------|-----|
| `gateway.tools_phase1` | `Phase1Tools(backend_manager, sessions?, auth_store?)`; `craft_apps()`, `craft_status(app?)`, `craft_run(app, command, params?, snapshot?)`, `craft_run_tool(app, tool, args?)`, `craft_app_call(app, method, params?)` — each `(…, user_id, session_id, raw_token?)`; `register_phase1_tools(mcp, backend_manager, sessions?, auth_store?) -> Phase1Tools`; `APP_REGISTRY`, `TOOL_NAMES` |
| Tool error contract | `ToolError("access denied")` (auth/roots), `ToolError("unknown app: …")`, backend failures surfaced with safe messages |

---

## 2. Key Decisions

| Decision | Rationale |
|----------|-----------|
| Tools re-check allowlist for direct calls; middleware remains primary enforcer | Defense in depth: MCP path enforced by `AuthMiddleware`, direct Python calls enforced by `_check` — same generic denial |
| Path-like params (`path/output_path/file/filename`) confined via `SessionRegistry.check_path`; other params forwarded untouched | Roots confinement without breaking backend contracts (gap fix: redaction must never mutate forwarded params) |
| `craft_run` wraps as `engine.execute{command, params, snapshot}` | Matches 08-REQUIRED-TOOLS.md §C3 guarded-execution shape; `snapshot` recorded, mechanics owned by TC-B |
| Generic `APP_REGISTRY` (cli/args/description/capabilities) | Other 9 apps light up as registry entries with no code changes (TC-A-00 responsibility 3) |
| Closer arch updates scoped to component-overview + api-contracts + matrix + coverage-map | data-model already covers SESSION/TOKEN/ALLOWLIST/ROOT; no schema change in TC-A |

### Gap analysis (TC-A-01 review — closer duty)

| # | Finding | Disposition |
|---|---------|-------------|
| 1 | `_confine_params` applied `redact_value` to forwarded params when sessions is None — keys named `args`/`params` would be scrubbed before reaching the backend | **Fixed**: forward `dict(params)`; added `test_confine_forwards_params_intact_without_sessions` regression |
| 2 | `test_phase1` fixture used `__import__` hack for `TokenRecord` | **Fixed**: direct import |
| 3 | `FastMCP.lifespan` decorator does not exist in 2.14.5 (found/fixed in TC-A-01) | Already fixed via constructor param — verified correct, no further action |
| 4 | Real-CLI proxy path unexercised (no pilot CLIs installed) | **Known limitation** (below); fake fallback covers all paths; `AppBackend` code reviewed + `status()` degraded path tested |
| 5 | `craft_run` envelope shape vs real CLI `engine.execute` contract unverified | **Assumption documented**: fake accepts the envelope; re-verify against real CLIs when available (TC-B) |

---

## 3. Gate Results

| Gate | Result | Notes |
|------|--------|-------|
| Pre-check test suite (Task 0.2) | ✅ 47 passed (TC-A-01 baseline) | no regressions |
| Post-implementation suite (Task 6) | ✅ 67 passed, 0 failed | `python3 -m pytest gateway/tests/ -q` from repo root |
| Coverage vs baseline | ✅ 47 → 67 (+20), no regressions | greenfield package, all modules exercised |
| Typecheck (compileall) | ✅ 0 errors | `python3 -m compileall -q gateway` |
| Lint (ruff check + format) | ✅ 0 errors, all formatted | 🔴 MANDATORY from TC-X-02 — met |
| Coverage vs target | ✅ 61 tests for SW-REQ-GW-CORE | recorded in coverage-map |
| TC-A integration tests (Task 8) | ✅ 6 passed | `test_integration_tc_a.py` |
| SYS3 smoke (Task 8) | ✅ PASS (stdio + http) | below |

## 3.5 Logger Evidence (mandatory)

| Item | Evidence |
|------|----------|
| Event names and allow-listed fields | `tool_egress` (tool/app/command/method/count/ok) added by all 5 tools; `phase1_registered`; existing `tool_ingress/auth_decision/backend_*` from TC-A-01 |
| Request/user/session propagation | Every tool logs ingress with `user_id/session_id` via `log_tool_ingress`; egress carries tool/app context |
| Redaction/no-secret tests | `test_phase1.py::test_tool_logs_carry_no_secrets` (token + document content absent); `_confine_params` never logs raw params |
| Sink and failure behavior | Tools log to `gateway` operational logger; auth denials to `gateway.audit`; backend failures logged at proxy boundary |
| Audit/metrics separation | Unchanged from TC-A-01 (distinct logger names; metrics logger reserved) |

---

## 4. Handoff for TC-B-01 (Verification Tools)

**Entry point**: `gateway/tools_phase1.py::Phase1Tools` + `register_phase1_tools` — build Phase-2 tools (`craft_look`, `craft_snapshot`/`craft_restore`, `craft_record`, `craft_assert`) in a new `gateway/tools_phase2.py` following the same pattern (`_check` → confine → backend → redacted egress log), registered alongside Phase-1 in `main()`.

**Wiring chain** (entry → new code, trigger):
`python -m gateway.main --transport stdio|http` → `main()` (`gateway/main.py:130`) → `create_gateway()` (`gateway/main.py:44`, auth middleware + lifespan) → `register_phase1_tools()` (`gateway/tools_phase1.py:330`) → `@mcp.tool craft_*` → `Phase1Tools` impl → `BackendManager.backend(app)` (`gateway/backends.py:378`) → `<app>-cli mcp` or `FakeAppBackend`. Trigger: MCP client `call_tool("craft_status", {"_gateway_token": token, "app": "photocraft"})`; direct: `await impl.craft_run(app=…, command=…, params=…, user_id=…, session_id=…, raw_token=…)`.

**What you inherit**:

- Auth: `AuthStore.mint/authenticate/authorize/revoke`; `AuthMiddleware`; allowlists are per-token tool-name sets (`"*"` = all). Example: `raw, rec = store.mint("agent1", {"craft_status", "craft_look"})`.
- Sessions/roots: `SessionRegistry.create(session_id, user_id, roots, key_id)`; `check_path(session_id, path)` raises `RootsViolation` on escape — reuse for snapshot/artifact paths.
- Backends: `await manager.backend(app)` → `.call_tool(method, params)` / `.status()` / `.list_tools()`; `FakeAppBackend` canned methods: `doc_inspect`, `engine.execute`, `render_preview`.
- Registry: `APP_REGISTRY` in `tools_phase1.py` — add capability flags as needed; keep generic (no per-app code).
- Logger: `log_tool_ingress`, `safe_event`, `redact_value`; never log raw params/bodies/content.

**What is NOT implemented yet** (stubs — TC-B owns):

- Phase-2 verification tools (`craft_look`, `craft_snapshot`/`craft_restore`, `craft_record`, `craft_assert`).
- `snapshot: true` in `craft_run` is recorded but not executed (no snapshot mechanics yet).
- Real pilot CLI verification (fakes active; `AppBackend` real path implemented but unexercised live).

**Run tests**: `python3 -m pytest gateway/tests/ -q` from repo root. Lint: `python3 -m ruff check gateway/ && python3 -m ruff format --check gateway/`. Compile: `python3 -m compileall -q gateway`.

---

## ⚠️ Known Issues / Limitations (if any)

- No pilot CLI binaries installed → `BackendManager(use_fake=True)` auto-fallback active everywhere; SYS3 smoke used fakes (documented). Re-verify against real `<app>-cli mcp` when available.
- `require_auth=False` mode exists for local stdio/tests; production HTTP must keep default `require_auth=True`.
- `craft_run` `engine.execute` envelope shape assumed (matches spec §C3); confirm against real CLI contract.
- No coverage-percentage tooling target configured; test counts (67) are the baseline.

---

## Traceability

| Level | ID | Artifact |
|-------|-----|---------|
| SYS1 | SYS1-001 | Epic: EPIC_001_CRAFTER_GATEWAY.md |
| SWE1 | SWE1-A | TC: TC-A-00_COMPONENT_DEFINITION.md |
| SWE3 | SWE3-A-02 | Issue: TC-A-02_PHASE1_TOOLS_AND_CLOSER.md |
| SWE4 | test_phase1 | Tests: `gateway/tests/test_phase1.py` (14) |
| SWE5 | self-verify | Tests: `gateway/tests/test_integration_tc_a.py` (6) |

---

## Self-verification (no-reviews mode)

Gate table (STEP D1–D5, all from repo root):

| Gate | Command | Exit | Result |
|------|---------|------|--------|
| D1 Lint | `python3 -m ruff check gateway/` + `ruff format --check gateway/` | 0 | 0 errors, 12 files formatted |
| D2 Typecheck/build | `python3 -m compileall -q gateway` | 0 | 0 errors |
| D3 Tests (issue + module suite) | `python3 -m pytest gateway/tests/ -q` | 0 | 67 passed (61 unit + 6 integration), 0 failed; baseline 47 → no regressions |
| D4 Smoke through wiring | stdio-path: in-memory `Client` over `create_gateway()+register_phase1_tools` → `craft_status` lists 3 pilots; HTTP-path: live uvicorn :18787 + real `Client('http://127.0.0.1:18787/mcp')` → `craft_status` lists 3 pilots | 0 | SYS3 PASS both transports (fakes documented; bare-TestClient POST correctly rejected — needs running server) |
| D5 Self-checklist | every file maps to a requirement; every requirement has impl + test; callers verified (greenfield + TC-A-01 handoff); no `any`/suppression; no secrets in logs (tested); all issue boxes ticked | — | yes to all |

Requirement → `file:line` → test → status:

| Requirement | Implementation | Test | Status |
|-------------|----------------|------|--------|
| `craft_apps/status/run/run_tool/app_call` + allowlist + roots | `gateway/tools_phase1.py:47` (`Phase1Tools`), `:330` (`register_phase1_tools`) | `test_phase1.py` (14) | ✅ |
| Pilot registry (generic for other 9) | `gateway/tools_phase1.py:36` (`APP_REGISTRY`) | `test_registry_pilot_only_generic_shape` | ✅ |
| Wire tools into `main.py` | `gateway/main.py:130` | `test_register_phase1_tools_wires_all_five` + integration | ✅ |
| Gap analysis of TC-A-01 | §2 table above | gap-fix regression test | ✅ (2 fixed, 3 documented) |
| Integration tests | `gateway/tests/test_integration_tc_a.py` | 6 passed | ✅ |
| Arch updates (component-overview, api-contracts) | diagrams (see §1 Changed Files) | — | ✅ |
| Traceability (matrix + coverage-map SW-REQ-GW-CORE) | traceability (see §1) | — | ✅ |
| SYS3 smoke (start gateway, call `craft_status`) | smoke commands in D4 | stdio + http PASS | ✅ |
| Logger (ingress/egress, redaction, audit/metrics) | tools log via `gateway/logger.py` | `test_tool_logs_carry_no_secrets` | ✅ |

Wiring chain proof: `python -m gateway.main --help` (entrypoint) → `create_gateway()` + `register_phase1_tools()` → live uvicorn server :18787 serving `/mcp` → real MCP client `call_tool('craft_status', {'_gateway_token': …})` → proxied `FakeAppBackend.doc_inspect` → 3 pilot apps with documents returned. Observable effect verified on both transports.

Residual risks / limitations / open questions:

- Real-CLI paths (proxy + envelope shape) unexercised — no pilot CLIs installed; TC-B should re-verify when CLIs exist.
- No config-file/secret-management layer for tokens (in-memory `AuthStore` only) — out of TC-A scope; TC-B/C may add.
- Coverage % tooling has no target; counts are the baseline.

Independent review intentionally omitted — TC-A is declared `no-reviews`; gap analysis is inherited by the TC closer (TC-A-02, this issue).

## Lane 5 audit (2026-10-12) — executed evidence

- Re-ran `python3 -m pytest gateway/tests/ -q` → **188 passed, 9 skipped** (9 skipped = real-CLI tests: no `*-cli` binaries; incl. `test_integration_tc_a.py` 6 SWE5 green).
- Live in-memory gateway: **12 tools** reachable; `craft_status(photocraft)` → `"running":"fake","mode":"fake"`; no `*-cli` on PATH → FakeAppBackend active.
- Gate verdict: Phase-1 tools + fake-mode integration backed ✅; real-CLI proxy + `engine.execute` envelope shape NOT backed.
- TODO (unbacked by real run): (1) re-verify `craft_run` envelope against the real CLI contract when binaries exist; (2) token persistence (still in-memory `AuthStore`).
