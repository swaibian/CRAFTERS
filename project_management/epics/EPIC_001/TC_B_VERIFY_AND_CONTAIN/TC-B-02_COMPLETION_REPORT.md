# TC-B-02: Containment + Docker + Closer — Completion Report

**Issue**: TC-B-02
**Component**: Verify + Contain
**V-Model**: SWE3-B-02
**Type**: 🔨 IMPLEMENTATION
**Status**: ⚠️ Partial — fake-backend only (downgraded by Lane 5 audit 2026-10-12; was ✅ Complete)
**Completed**: 2026-10-11

---

## 1. What Was Built

### New Files

| File | Purpose | Serves |
|------|---------|--------|
| `gateway/tests/test_containment.py` | 28 SWE4 tests: traversal/absolute/sibling-prefix, second roots, missing-parent creation paths, read/write parity, symlink escape denied / inside allowed / dangling-outside denied / dangling-inside allowed, cross-session/unknown/no-roots, Phase-1 + Phase-2 tool confinement, snapshot session-scope, audit redaction (no paths in any record) | SWE4 containment |
| `gateway/tests/test_integration_tc_b.py` | 6 SWE5 tests via real `create_gateway` + both tool registers + middleware: 10-tool reachability, measured-without-evidence rejected, snapshot→edit→look→assert→record + auto-snapshot `snapshot_token`, restore returns prior revision, escape rejected on run/look, verify-scoped token allows look but not run | SWE5 self-verify |
| `deploy/Dockerfile` | Python 3.12-slim gateway image: fastmcp install, pilot CLI install hooks (commented, uncomment when release zips available), non-root user, `/work` mount, http entrypoint | containerised local run |
| `deploy/docker-compose.yml` | `crafters` stack: gateway on `127.0.0.1:8787`, `crafter-work` volume, json-file log rotation, healthcheck; secrets wiring commented with docs | local run composition |
| `gateway/requirements.txt` | `fastmcp>=2.14` (image + fresh-checkout installs) | packaging |

### Changed Files

| File | Change |
|------|--------|
| `gateway/main.py` | Token bootstrap: `provision_tokens()` (`CRAFTER_DEV_TOKEN` loopback-only wildcard, `CRAFTER_TOKENS_FILE`/`--tokens-file` JSON provisioning, fail-closed empty store otherwise); `--work-dir` default roots + `default` session; `--dev-token-ok` override; summary lines print `key_id` only, never tokens |
| `project_management/architecture/diagrams/component-overview.md` | TC-B blocks: entrypoint bootstrap, Phase-2 tools, SnapshotStore/RecordStore, hardened SessionRegistry, container; GW header ✅ TC-A ✅ TC-B |
| `project_management/architecture/diagrams/api-contracts.md` | Phase-2 tool contracts, containment contract, local-run contract rows; snapshot→run→look→assert→restore→record sequence |
| `project_management/architecture/traceability/requirements-matrix.md` | SW-REQ-GW-VERIFY row filled (SWE4 files + counts, SWE5 self-verify + SYS3 smoke) → ✅ |
| `project_management/architecture/traceability/coverage-map.md` | SW-REQ-GW-VERIFY row filled (63 tests) → ✅ |

### APIs / Contracts Defined

| Module | API |
|--------|-----|
| `gateway.main` | `provision_tokens(store, *, host, dev_token_ok=False, tokens_file=None) -> list[str]`; `main()` flags `--tokens-file`, `--dev-token-ok`, `--work-dir`; env `CRAFTER_DEV_TOKEN`, `CRAFTER_TOKENS_FILE`, `CRAFTER_WORK_DIR` |
| Tokens file | JSON `{raw_token: {"user_id", "allowlist": [...]}}` |
| Error contract | Unchanged: `ToolError("access denied")` (auth/roots), measured-without-evidence, session-scoped restore |

---

## 2. Key Decisions

| Decision | Rationale |
|----------|-----------|
| Dev token refused on non-loopback binds without `--dev-token-ok` | A wildcard token must never cross the network by accident; explicit override for testing |
| Dangling symlink resolving outside = denied (deny-by-default) | `realpath` sees through dangling links; grace applies only when nothing resolves outside roots |
| `.` resolves to the root itself (allowed) | It names no location outside the session; treating it as escape would break root-relative tooling |
| Audit records carry `{session_id, ok, error_code}` only — not even parent paths | Parent of an escape attempt may itself be sensitive (`/etc`); tested |
| Docker image documents fake-backend mode as the default without pilot CLIs | CLIs are not public packages; gateway + all tools work regardless |

### Gap analysis (TC-B-01 review — closer duty)

| # | Finding | Disposition |
|---|---------|-------------|
| 1 | Symlink escapes unhandled (`check_path` lexical only at TC-B-01 handoff) | **Fixed upstream of this issue**: `backends.py` already carries the realpath second opinion + audit; this issue added the 4 symlink tests proving it |
| 2 | No way to start the gateway with a usable token (empty store denies everything) | **Fixed**: `provision_tokens()` + dev/file bootstrap, smoke-tested on both transports |
| 3 | No `deploy/` dir existed | **Fixed**: Dockerfile + compose + requirements.txt |
| 4 | `main()` had no `--work-dir`/default session → Phase-2 session-scoped tools unusable from a bare start | **Fixed**: `--work-dir` creates roots + `default` session |
| 5 | Real-CLI proxy + `engine.restore` rollback unexercised | **Known limitation** (below); fake covers all paths |
| 6 | Visual asserts coarse on fakes | **Known limitation**; structural default documented |

---

## 3. Gate Results

| Gate | Result | Notes |
|------|--------|-------|
| Pre-check test suite (Task 0.2) | ✅ 96 passed (TC-B-01 baseline) | no regressions |
| Post-implementation suite (Task 6) | ✅ 130 passed, 0 failed | `python3 -m pytest gateway/tests/ -q` from repo root (+34) |
| Coverage vs baseline | ✅ 96 → 130, no regressions | containment + integration + bootstrap |
| Typecheck (compileall) | ✅ 0 errors | `python3 -m compileall -q gateway` |
| Lint (ruff check + format) | ✅ 0 errors, all formatted | 🔴 MANDATORY from TC-X-02 — met |
| Coverage vs target | ✅ 63 tests for SW-REQ-GW-VERIFY | recorded in coverage-map |
| TC-B integration tests (Task 8) | ✅ 6 passed | `test_integration_tc_b.py` |
| SYS3 smoke (Task 8) | ✅ PASS (in-memory + live HTTP) | below |

## 3.5 Logger Evidence (mandatory)

| Item | Evidence |
|------|----------|
| Event names and allow-listed fields | `roots_decision` (session_id/ok/error_code) on every `check_path`; existing `tool_ingress/egress`, `snapshot_*`, `record_create`, `assert_result`, `auth_decision` |
| Request/user/session propagation | Roots decisions carry `session_id`; tool + auth events carry `user_id/session_id/key_id` |
| Redaction/no-secret tests | `test_denial_audit_carries_no_paths`, `test_allow_audit_carries_no_paths` (paths absent from ALL records), `test_tool_escape_logs_no_content` (no token/path/content) |
| Sink and failure behavior | Roots decisions → `gateway.audit`; tool events → `gateway`; close failures logged not raised (unchanged) |
| Audit/metrics separation | Unchanged (distinct logger names; metrics reserved) |

---

## 4. Handoff for TC-C-01 (Accessibility Refs)

**Entry point**: `gateway/perception.py` (to create) — AccessKit proxy + canvasRect synthesis + `query_map` backing; upstream PR drafts for pdfcraft + photocraft. Build on `Phase2Tools.craft_look` (metadata + hash) as the perception transport.

**Wiring chain** (entry → new code, trigger):
`python -m gateway.main --transport http --port 8787` (with `CRAFTER_DEV_TOKEN` + `CRAFTER_WORK_DIR`) → `main()` (`gateway/main.py:main`) → `create_gateway()` (auth middleware + lifespan) → `provision_tokens()` → `register_phase1_tools()` + `register_phase2_tools()` (shared `SnapshotStore`) → `@mcp.tool craft_*` (10 tools) → `BackendManager.backend(app)` (`gateway/backends.py:BackendManager.backend`) → `<app>-cli mcp` or `FakeAppBackend`. Trigger: `call_tool("craft_snapshot", {"_gateway_token": token, "app": "photocraft"})`; Bearer-header path verified live (valid → 10 tools listed, call works; wrong → empty list).

**What you inherit**:

- Verify tools: `craft_look(app, scope?, index?, region?, max_side?, detail?, layer?, path?)` → `{revision, content_hash}` metadata-only; `craft_snapshot/restore` session-scoped; `craft_record` rejects unbacked measured; `craft_assert` structural default. Example: `snap = await impl.craft_snapshot(app="photocraft", user_id="u", session_id="s")` → `{"token": "snap_…", "revision": N}`.
- Containment: `SessionRegistry.check_path(session_id, path)` — lexical + realpath symlink check + audit; `RootsViolation` on escape. Use for every new file path.
- Local run: `CRAFTER_DEV_TOKEN=… CRAFTER_WORK_DIR=/tmp/work python3 -m gateway.main --transport http --port 8787`; `cd deploy && docker compose up --build`.
- Tests: `gateway/tests/test_containment.py` (28), `test_integration_tc_b.py` (6). Run: `python3 -m pytest gateway/tests/ -q` from repo root. Lint: `python3 -m ruff check gateway/ && python3 -m ruff format --check gateway/`. Compile: `python3 -m compileall -q gateway`.

**What is NOT implemented yet** (TC-C owns):

- `gateway/perception.py` (no file yet); upstream PR drafts; `docs/a11y-contribution-pattern.md`.
- Real pilot CLI verification (fakes active; all proxy paths implemented).

**Run tests**: `python3 -m pytest gateway/tests/ -q` from `/Users/wodivity-mw/01_Swaibian/Swaibian-Main_Office/05_Products/Crafters`.

---

## ⚠️ Known Issues / Limitations (if any)

- No pilot CLI binaries installed → fake backends everywhere; `engine.restore` rollback + pixel-diff unexercised against real CLIs.
- Dev-token bootstrap is local-run convenience; production needs file-based provisioning or own `create_gateway` wiring (documented in `main.py` + compose).
- No coverage-% tooling; test counts (130) are the baseline.
- Raw POST without MCP session headers 400s at the protocol layer (streamable_http requires session init) — not an auth finding; Bearer path verified via real client.

---

## Traceability

| Level | ID | Artifact |
|-------|-----|---------|
| SYS1 | SYS1-001 | Epic: EPIC_001_CRAFTER_GATEWAY.md |
| SWE1 | SWE1-B | TC: TC-B-00_COMPONENT_DEFINITION.md |
| SWE3 | SWE3-B-02 | Issue: TC-B-02_CONTAINMENT_AND_CLOSER.md |
| SWE4 | test_containment | Tests: `gateway/tests/test_containment.py` (28) |
| SWE5 | self-verify | Tests: `gateway/tests/test_integration_tc_b.py` (6) |

---

## Self-verification (no-reviews mode)

Gate table (STEP D1–D5, all from repo root):

| Gate | Command | Exit | Result |
|------|---------|------|--------|
| D1 Lint | `python3 -m ruff check gateway/` + `ruff format --check gateway/` | 0 | 0 errors, 17 files formatted |
| D2 Typecheck/build | `python3 -m compileall -q gateway` | 0 | 0 errors |
| D3 Tests (issue + module suite) | `python3 -m pytest gateway/tests/ -q` | 0 | 130 passed (96 baseline + 34), 0 failed |
| D4 Smoke through wiring | in-memory full verify flow (snapshot→run→look→assert→record, both rejections) + live uvicorn :18799 `craft_status` + Bearer-header list (10 tools) + call on :18797 | 0 | SYS3 PASS: status lists 3 pilots; snapshot rev 1 → run rev 2 → hash `sha256:fake` → assert pass → record id; unbacked measured + `/etc/passwd` rejected; wrong bearer → empty list |
| D5 Self-checklist | every file maps to a requirement; every requirement has impl + test; callers verified (all new symbols; bootstrap re-verified via smoke); no suppression; no secrets/paths in logs (tested); all issue boxes ticked | — | yes to all |

Requirement → `file:line` → test → status:

| Requirement | Implementation | Test | Status |
|-------------|----------------|------|--------|
| Roots on every file path + symlink hardening + audit | `gateway/backends.py` (`SessionRegistry.check_path`, `_audit_path_decision`) | `test_containment.py` (28) | ✅ |
| `deploy/Dockerfile` + compose | `deploy/` | build-file review + compose config shape | ✅ |
| Token bootstrap + work-dir (startable gateway) | `gateway/main.py` (`provision_tokens`, `--work-dir`) | smoke (dev token provisions, file tested) | ✅ |
| Gap analysis of TC-B-01 | §2 table above | — | ✅ (4 fixed, 2 known) |
| Integration tests | `gateway/tests/test_integration_tc_b.py` | 6 passed | ✅ |
| Arch updates (overview, api-contracts) | diagrams (see §1) | — | ✅ (data-model + flow already covered TC-B rows) |
| Traceability (matrix + coverage-map SW-REQ-GW-VERIFY) | traceability (see §1) | — | ✅ |
| SYS3 smoke | D4 commands | in-memory + live HTTP PASS | ✅ |
| Logger (roots audit, redaction) | `roots_decision` events | redaction tests | ✅ |

Wiring chain proof: `CRAFTER_DEV_TOKEN=… python3 -m gateway.main --transport http` → uvicorn serves `/mcp` → real MCP client with `Authorization: Bearer` lists 10 tools → `craft_status` returns 3 pilots; stdio path covered by in-memory Client across all 10 tools with allowlist + roots enforcement live.

Residual risks / limitations / open questions:

- Real-CLI paths unexercised — no pilot CLIs installed; re-verify when available.
- Coverage % tooling has no target; counts are the baseline.

Independent review intentionally omitted — TC-B is declared `no-reviews`; gap analysis is inherited by the TC closer (TC-B-02, this issue).

## Lane 5 audit (2026-10-12) — executed evidence

- Re-ran `python3 -m pytest gateway/tests/ -q` → **188 passed, 9 skipped** (9 skipped = real-CLI tests: no binaries; incl. 28 containment + 6 TC-B integration green).
- Deploy re-verified this lane: `docker compose -f deploy/docker-compose.yml config --quiet` → OK; `docker compose build` → gateway/controller/view images Built.
- Fixed this lane: gateway healthcheck now treats MCP 4xx (no bearer/session) as healthy — only connection failure/5xx is unhealthy (`deploy/docker-compose.yml`).
- Gate verdict: containment + fake-mode integration backed ✅; real-CLI containment re-verify NOT backed.
- TODO (unbacked by real run): (1) re-verify containment against real `<app>-cli mcp` when available.
