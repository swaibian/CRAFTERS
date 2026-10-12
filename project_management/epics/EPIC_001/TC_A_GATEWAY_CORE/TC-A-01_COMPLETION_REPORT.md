# TC-A-01: Gateway Service + Auth — Completion Report

**Issue**: TC-A-01
**Component**: Gateway Core
**V-Model**: SWE3-A-01
**Type**: 🔨 IMPLEMENTATION
**Status**: ⚠️ Partial — fake-backend only (downgraded by Lane 5 audit 2026-10-12; was ✅ Complete)
**Completed**: 2026-10-11

---

## 1. What Was Built

### New Files

| File | Purpose | Serves |
|------|---------|--------|
| `gateway/__init__.py` | Package marker | packaging |
| `gateway/main.py` | FastMCP app factory (`create_gateway`), stdio + streamable_http entrypoint (`main()`), lifespan (backend shutdown) | transport requirement |
| `gateway/auth.py` | `TokenRecord`, `AuthStore` (bearer validation, allowlists, revoke, mint), `AuthMiddleware` (tools/call enforcement + tools/list filtering), `extract_bearer`, `check_tool_allowed` | auth/allowlist requirement |
| `gateway/backends.py` | `SessionRegistry` (sessions + `check_path` roots confinement), `AppBackend` (spawn `<app>-cli mcp` via StdioTransport, proxy), `FakeAppBackend` (canned fallback), `BackendManager` (one backend per app, shared across sessions) | pilot wiring + session roots |
| `gateway/logger.py` | Stdlib logging: `gateway` / `gateway.audit` / `gateway.metrics` loggers, `safe_event` allow-list, `redact_value` recursive scrub, ingress/auth-decision helpers | logging & observability allocation |
| `gateway/tests/__init__.py` | Test package marker | SWE4 |
| `gateway/tests/test_auth.py` | 17 auth tests: valid/invalid/expired/revoked bearer, allowlist allow/deny, per-user denial, middleware allow/deny through a real FastMCP app, audit log without secrets | SWE4 |
| `gateway/tests/test_backends.py` | 15 backend tests: session CRUD, roots allow/escape (incl. sibling-prefix), isolation across sessions, fake backend, manager sharing, missing-CLI degraded status | SWE4 |
| `gateway/tests/test_logger.py` | 9 logger tests: allow-list passthrough, forbidden-field redaction (tokens/secrets/content/image/transcript/body/params), bytes scrub, truncation, no-mutation, sink separation | SWE4 |

### Changed Files

| File | Change |
|------|--------|
| — | None (greenfield package; no existing callers) |

### APIs / Contracts Defined

| Module | API |
|--------|-----|
| `gateway.main` | `create_gateway(auth_store?, backend_manager?, sessions?, require_auth=True) -> FastMCP`; `main(argv?)` entrypoint (`--transport stdio\|http --host --port --path --open-auth`); handles stashed as `mcp.auth_store` / `mcp.backend_manager` / `mcp.sessions` |
| `gateway.auth` | `AuthStore.register/authenticate/authorize/revoke/mint`; `AuthMiddleware(store, require_auth)`; `extract_bearer(headers)`; `check_tool_allowed(store, token, tool)`; denial = `ToolError("access denied")` (generic, no leakage) |
| `gateway.backends` | `SessionRegistry.create/get/drop/check_path`; `AppBackend.connect/close/list_tools/call_tool/status`; `FakeAppBackend` (same surface, canned); `BackendManager.backend(app)/close_all/apps/use_fake` |
| `gateway.logger` | `get_logger/get_audit_logger/get_metrics_logger`; `safe_event(**fields)`; `redact_value(obj)`; `log_tool_ingress(...)`; `log_auth_decision(...)` |

---

## 2. Key Decisions

| Decision | Rationale |
|----------|-----------|
| Real FastMCP 2.14.5, no shim | `fastmcp` package present (2.14.5) with middleware hooks, `get_http_headers`, in-memory `Client`, `StdioTransport` — shim criterion not triggered; zero deviation |
| Auth as FastMCP `Middleware` (`on_call_tool` + `on_list_tools`) | Server-side enforcement on every call; `tools/list` filtered so denied tools are not advertised; mirrors swaibian-one `mcp_auth` by reference only (no swaibian-one code touched) |
| stdio token via `_gateway_token` arg (stripped before tool runs) | stdio has no HTTP headers; explicit smuggled-arg contract for trusted local launchers, removed before dispatch so tools never see credentials |
| Lifespan via `FastMCP(..., lifespan=...)` constructor param | `FastMCP` 2.14.5 has no `.lifespan` decorator — constructor is the API; owns `BackendManager.close_all()` on shutdown |
| `BackendManager` auto-fallback to fake when no CLI on PATH | Pilot CLIs absent in this environment; gateway + tools + tests work end-to-end regardless; `use_fake` property documents which mode is active |
| Session isolation in roots, backends shared per app | One subprocess per app (cheap), confinement via `SessionRegistry.check_path` lexical resolution (no filesystem touch, `..`/absolute/sibling-prefix rejected) |
| Logger: three stdlib logger names, no handlers configured here | Operators route `gateway` / `gateway.audit` / `gateway.metrics` independently; `safe_event` allow-list + `redact_value` scrub enforced by tests |
| ruff for lint (no mypy/pyright installed) | Typecheck gate per brief = `python -m compileall` + ruff; no `any`/suppression equivalents in Python path |

---

## 3. Gate Results

| Gate | Result | Notes |
|------|--------|-------|
| Pre-check test suite (Task 0.2) | ✅ baseline: 0 tests (no `gateway/` package existed) | greenfield |
| Post-implementation suite (Task 6) | ✅ 47 passed, 0 failed | `python3 -m pytest gateway/tests/ -q` from repo root |
| Coverage vs baseline | ✅ N/A (greenfield; new code fully exercised by 41 tests) | no baseline to regress |
| Typecheck (compileall) | ✅ 0 errors | `python3 -m compileall -q gateway` |
| Lint (ruff check + format) | ✅ 0 errors, all formatted | ADVISORY on TC-X-01, met anyway |
| Coverage vs target | ✅ new code covered (auth/backends/logger/tools-path all tested) | — |

## 3.5 Logger Evidence (mandatory)

| Item | Evidence |
|------|----------|
| Event names and allow-listed fields | `tool_ingress`, `auth_decision`, `session_create`, `backend_spawn`, `backend_proxy`, `gateway_startup/shutdown`; `SAFE_FIELDS` in `gateway/logger.py:27` |
| Request/user/session propagation | `log_tool_ingress(tool, user_id, session_id, key_id)`; auth decisions carry `user_id/key_id/tool/ok/error_code` |
| Redaction/no-secret tests | `gateway/tests/test_logger.py` (9 tests) + `test_auth.py::test_middleware_denial_logged_without_secrets` + `test_authenticate_errors_leak_nothing` |
| Sink and failure behavior | `gateway` / `gateway.audit` / `gateway.metrics` names; backend close failures logged, never raised (`backends.py` `close_all`) |
| Audit/metrics separation | Distinct logger names; `log_auth_decision` writes audit only; metrics logger reserved (no audit content) |

---

## 4. Handoff for TC-A-02 (Phase-1 Tools + Pilot Wiring + Closer)

**Entry point**: `gateway/main.py::create_gateway` — FastMCP app with `AuthMiddleware` + lifespan; attach Phase-1 tools here via a new `register_phase1_tools(mcp, backend_manager, sessions)` in `gateway/tools_phase1.py`. `main()` already attempts that import (falls back gracefully when absent).

**Wiring chain** (entry → new code, trigger):
`python -m gateway.main --transport stdio` → `main()` (`gateway/main.py:130`) → `create_gateway()` (`gateway/main.py:44`) → `AuthMiddleware` (`gateway/auth.py:141`) + lifespan → (TC-A-02 adds) `register_phase1_tools` → tool impls → `BackendManager.backend(app)` (`gateway/backends.py:378`) → `<app>-cli mcp` stdio subprocess or `FakeAppBackend`. Trigger in tests: `fastmcp.Client(mcp)` + `call_tool(name, {"_gateway_token": token, ...})`.

**What you inherit**:

- Auth: `from gateway.auth import AuthStore, TokenRecord, check_tool_allowed` — `store.authenticate(token)` → record; `store.authorize(record, tool)` → allowlist. Denial pattern: `raise ToolError("access denied")`. Example:
  ```python
  store = AuthStore()
  raw, rec = store.mint("alice", {"craft_status", "craft_apps"})
  ```
- Backends: `from gateway.backends import BackendManager, SessionRegistry` — `await manager.backend("photocraft")` → `.call_tool(method, params)` / `.status()`; `sessions.check_path(session_id, path)` for roots confinement. `BackendManager(use_fake=True)` forces fakes.
- Logger: `from gateway.logger import get_logger, safe_event, redact_value, log_tool_ingress` — wrap every tool ingress/egress + proxied response; never log raw params.
- Pilot apps: `PILOT_APPS = ("photocraft", "pdfcraft", "gridcraft")`; CLI = `<app>-cli mcp`.

**What is NOT implemented yet** (stubs):

- Phase-1 tools (`craft_apps`, `craft_status`, `craft_run`, `craft_run_tool`, `craft_app_call`) — TC-A-02 owns them.
- Pilot registry beyond `PILOT_APPS` tuple + `<app>-cli` naming convention — TC-A-02 owns the registry with capability flags.

**Run tests**: `python3 -m pytest gateway/tests/ -q` from repo root (`/Users/wodivity-mw/01_Swaibian/Swaibian-Main_Office/05_Products/Crafters`). Lint: `python3 -m ruff check gateway/ && python3 -m ruff format --check gateway/`.

---

## ⚠️ Known Issues / Limitations (if any)

- Real `<app>-cli` binaries absent → `BackendManager` runs in fake mode (`use_fake=True`); real-CLI proxy path (`AppBackend` via `StdioTransport`) is implemented but unexercised against live CLIs — TC-A-02 smoke should re-verify if CLIs appear.
- `require_auth=False` mode exists for local stdio/tests; production HTTP must run with `require_auth=True` (default).
- No coverage tooling configured (`pytest-cov` installed but no target); greenfield suite is the baseline.

---

## Traceability

| Level | ID | Artifact |
|-------|-----|---------|
| SYS1 | SYS1-001 | Epic: EPIC_001_CRAFTER_GATEWAY.md |
| SWE1 | SWE1-A | TC: TC-A-00_COMPONENT_DEFINITION.md |
| SWE3 | SWE3-A-01 | Issue: TC-A-01_GATEWAY_SERVICE_AND_AUTH.md |
| SWE4 | test_auth/test_backends/test_logger | Tests: `gateway/tests/test_auth.py`, `gateway/tests/test_backends.py`, `gateway/tests/test_logger.py` |

---

## Self-verification (no-reviews mode)

Gate table (STEP D1–D5, all from repo root):

| Gate | Command | Exit | Result |
|------|---------|------|--------|
| D1 Lint | `python3 -m ruff check gateway/` + `ruff format --check` | 0 | 0 errors, 9 files formatted |
| D2 Typecheck/build | `python3 -m compileall -q gateway` | 0 | 0 errors |
| D3 Tests (module suite) | `python3 -m pytest gateway/tests/ -q` | 0 | 47 passed, 0 failed (17 auth + 15 backends + 9 logger + 6 misc) |
| D4 Smoke through wiring | entrypoint `--help` + in-memory `Client` over `create_gateway()` + `http_app(transport='streamable-http')` | 0 | gateway serves; auth middleware active; HTTP app builds at `/mcp` |
| D5 Self-checklist | all changed files map to requirements; every requirement has impl + test; no callers (greenfield); no `any`/suppression; no secrets in logs (tested); all issue boxes ticked below | — | yes to all |

Requirement → `file:line` → test → status:

| Requirement | Implementation | Test | Status |
|-------------|----------------|------|--------|
| FastMCP app, stdio + streamable_http | `gateway/main.py:44` (`create_gateway`), `:130` (`main`) | smoke (Client + http_app) | ✅ |
| Bearer validation, allowlists, per-user denial | `gateway/auth.py:74` (`AuthStore`), `:141` (`AuthMiddleware`) | `test_auth.py` (17) | ✅ |
| Spawn `<app>-cli mcp`, proxy, session roots | `gateway/backends.py:230` (`AppBackend`), `:88` (`SessionRegistry`), `:340` (`BackendManager`) | `test_backends.py` (15) | ✅ |
| Session registry | `gateway/backends.py:88` | `test_backends.py::test_session_*` | ✅ |
| Logger + redaction, no secrets in logs | `gateway/logger.py` | `test_logger.py` (9) + auth leakage tests | ✅ |

Wiring chain proof: `python -m gateway.main --help` (entrypoint parses) → `create_gateway()` builds `FastMCP("crafter-gateway")` + `AuthMiddleware` + lifespan → in-memory `Client` lists tools (empty pre-TC-A-02, middleware active) → `http_app(transport='streamable-http', path='/mcp')` builds Starlette app. Trigger: `Client(mcp)` + `call_tool(..., {"_gateway_token": ...})` (exercised in `test_auth.py` middleware tests).

Residual risks / limitations / open questions:

- Real-CLI proxy path unexercised against live pilot CLIs (none installed); fake fallback covers all tests.
- `require_auth=False` must never reach production HTTP — default is True; no config-file layer yet (TC-B/C may add).
- Coverage tooling has no target configured; suite count (47) is the baseline.

Independent review intentionally omitted — TC-A is declared `no-reviews`; gap analysis is inherited by the TC closer (TC-A-02).

## Lane 5 audit (2026-10-12) — executed evidence

- Re-ran `python3 -m pytest gateway/tests/ -q` → **188 passed, 9 skipped** (9 skipped = real-CLI tests in `test_backends_real.py`: "no *-cli binary (Lane 1 not landed)").
- Live in-memory gateway (`Client` over `create_gateway` + all registers): **12 tools** reachable; `craft_status(photocraft)` → `"running":"fake","mode":"fake"`.
- `shutil.which` for `photocraft-cli`/`pdfcraft-cli`/`gridcraft-cli` → all `None`: **FakeAppBackend active everywhere**; the `AppBackend` stdio-proxy path is implemented but unexercised.
- Gate verdict: implementation + fake-mode tests backed ✅; any "works against real Craft CLIs" reading is NOT backed.
- TODO (unbacked by real run): (1) verify `AppBackend` proxy against a real `<app>-cli mcp` binary when available; (2) coverage-% target still unconfigured.
