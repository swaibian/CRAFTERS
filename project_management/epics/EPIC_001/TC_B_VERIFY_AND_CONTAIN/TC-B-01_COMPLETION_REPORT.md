# TC-B-01: Verification Tools — Completion Report

**Issue**: TC-B-01
**Component**: Verify + Contain
**V-Model**: SWE3-B-01
**Type**: 🔨 IMPLEMENTATION
**Status**: ⚠️ Partial — fake-backend only (downgraded by Lane 5 audit 2026-10-12; was ✅ Complete)
**Completed**: 2026-10-11

---

## 1. What Was Built

### New Files

| File | Purpose | Serves |
|------|---------|--------|
| `gateway/snapshots.py` | `SnapshotStore` (token → app/session/revision/data-ref, session-scoped restore), `RecordStore` (claim ledger), `is_destructive_command` policy predicate | Snapshot/record mechanics |
| `gateway/tools_phase2.py` | `Phase2Tools` (5 tools with allowlist re-check + roots confinement + redacted logging), `register_phase2_tools(mcp, …)` wiring | Phase-2 tool surface |
| `gateway/tests/test_phase2.py` | 29 SWE4 tests: look scopes/details, snapshot/restore round-trip, record rejection of unbacked measured claims, structural + visual asserts, auto-snapshot hook, allowlist denial, log redaction, full wiring | SWE4 |

### Changed Files

| File | Change |
|------|--------|
| `gateway/tools_phase1.py` | `Phase1Tools` accepts shared `snapshots` store; `craft_run` auto-snapshot hook (`_maybe_auto_snapshot`) + `snapshot_token` in result; `register_phase1_tools` forwards the store |
| `gateway/main.py` | `main()` creates one shared `SnapshotStore` and registers Phase-1 + Phase-2 tools with it |

### APIs / Contracts Defined

| Module | API |
|--------|-----|
| `gateway.snapshots` | `SnapshotStore.create/restore/get/list_for_session/drop_session`; `RecordStore.create/list_for_session`; `is_destructive_command(command, params) -> bool`; `SnapshotError` |
| `gateway.tools_phase2` | `Phase2Tools(backend_manager, sessions?, auth_store?, snapshots?, records?)`; `craft_look(app, scope?, index?, region?, max_side?, detail?, layer?, path?)`, `craft_snapshot(app, label?) → {token, revision}`, `craft_restore(app, token) → {restored_to}`, `craft_record(claim, confidence, evidence?, note?) → {record_id, …}`, `craft_assert(app, expect, tolerance?) → {passed, observed, …}` — each `(…, user_id, session_id, raw_token?)`; `register_phase2_tools(mcp, …) -> Phase2Tools` |
| Tool error contract | `ToolError("measured claims require evidence")` (record), `ToolError("visual assertions require tolerance")` (assert), `ToolError("unknown snapshot"/"access denied"/"snapshot app mismatch")` (restore), `ToolError("unknown scope/detail/assertion")` |

---

## 2. Key Decisions

| Decision | Rationale |
|----------|-----------|
| `snapshots.py` is import-neutral (stdlib only) — both tool modules import it, it imports nothing | Avoids a Phase-1 ↔ Phase-2 import cycle for the shared policy predicate |
| One shared `SnapshotStore` across Phase-1 hook + Phase-2 tools (wired in `main()`) | Auto-snapshot tokens from `craft_run` must be restorable via `craft_restore` — separate stores would orphan them |
| `craft_look` returns metadata only (revision + content_hash), never pixels | Gateway never carries image bytes; the hash is what enables caching/diffing per spec A1 |
| Visual asserts coarse-but-deterministic on fakes (same revision ⇒ delta 0, else 1) | Real pixel-diff needs renderer-backed backends; structural asserts are the default per TC-00 decision |
| `engine.restore` probed opportunistically (`if "engine.restore" in tools`) | Fakes lack it — restore returns the prior revision regardless; real CLIs get actual rollback |
| Snapshot tokens secret (log prefix only); record ids public | Tokens grant restore power; ids are just references |
| Test bug fixed during execution (valid-token + different `user_id` label passed — correct, auth is token-based) | Replaced with genuinely unauthorized cases: bogus token + valid token with wrong-tool allowlist |

### Deviations from the issue plan

None material. Auto-snapshot hook lives in `tools_phase1.craft_run` (not a separate module) — it is 30 lines and belongs with the call it guards.

---

## 3. Gate Results

| Gate | Result | Notes |
|------|--------|-------|
| Pre-check test suite (Task 0.2) | ✅ 67 passed (TC-A-02 baseline) | compileall + ruff clean |
| Post-implementation suite (Task 6) | ✅ 96 passed, 0 failed | `python3 -m pytest gateway/tests/ -q` from repo root (+29) |
| Coverage vs baseline | ✅ 67 → 96, no regressions | all modules exercised incl. negative/unauthorized/redaction |
| Typecheck (compileall) | ✅ 0 errors | `python3 -m compileall -q gateway` |
| Lint (ruff check + format) | ✅ 0 errors, all formatted | MANDATORY from TC-X-02 — met |
| Coverage vs target | ✅ 29 tests for SW-REQ-GW-VERIFY | recorded for closer's coverage-map |

## 3.5 Logger Evidence (mandatory)

| Item | Evidence |
|------|----------|
| Event names and allow-listed fields | `tool_egress` (tool/app/revision/content_hash/count/ok) on all 5 tools; `snapshot_create`, `snapshot_auto`, `snapshot_restore` (app/session/revision); `record_create` (session/count); `assert_result` (app/session/count/ok); `phase2_registered` |
| Request/user/session propagation | Every tool logs ingress with `user_id/session_id` via `log_tool_ingress`; snapshot/record/assert events carry session + user |
| Redaction/no-secret tests | `test_phase2.py::test_phase2_logs_carry_no_secrets_content_or_pixels` (claim/note/image payload absent; snapshot token absent — prefix-only) |
| Sink and failure behavior | Tools log to `gateway` operational logger; denials surface as generic `ToolError` |
| Audit/metrics separation | Unchanged from TC-A (distinct logger names; metrics logger reserved) |

---

## 4. Handoff for TC-B-02 (Containment + Docker + Closer)

**Entry point**: `gateway/tools_phase2.py::Phase2Tools` + `register_phase2_tools` — harden roots on every file path, package the containerised local run, then close the TC.

**Wiring chain** (entry → new code, trigger):
`python -m gateway.main` → `main()` (`gateway/main.py:92`) → `create_gateway()` (`gateway/main.py:34`) → `register_phase1_tools()` (shared `SnapshotStore`) + `register_phase2_tools()` (`gateway/tools_phase2.py:register_phase2_tools`) → `@mcp.tool craft_*` → `Phase2Tools` impl → `BackendManager.backend(app)` (`gateway/backends.py:408`) → `FakeAppBackend`. Trigger: MCP client `call_tool("craft_snapshot", {"_gateway_token": token, "app": "photocraft"})`; direct: `await impl.craft_assert(app=…, expect=…, user_id=…, session_id=…, raw_token=…)`.

**What you inherit**:

- Phase-2 tools: `craft_look` (metadata + hash, path confined), `craft_snapshot`/`craft_restore` (session-scoped tokens), `craft_record` (measured-requires-evidence), `craft_assert` (structural default, visual opt-in + tolerance). Example: `snap = await impl.craft_snapshot(app="photocraft", user_id="alice", session_id="s1")` → `{"token": "snap_…", "revision": 1}`.
- Stores: `SnapshotStore` / `RecordStore` in `gateway/snapshots.py`; `is_destructive_command` predicate; `mcp.snapshots` / `mcp.records` handles stashed by `register_phase2_tools`.
- Auto-snapshot: `craft_run(snapshot=True)` or destructive command/batch auto-takes a snapshot and returns `snapshot_token` in the result.
- Logger: `snapshot_create/auto/restore`, `record_create`, `assert_result` events; renders by hash only.
- Tests: `gateway/tests/test_phase2.py` (29). Run: `python3 -m pytest gateway/tests/ -q` from repo root. Lint: `python3 -m ruff check gateway/ && python3 -m ruff format --check gateway/`. Compile: `python3 -m compileall -q gateway`.

**What is NOT implemented yet** (TC-B-02 owns):

- Roots enforcement audit on ALL file-bearing tools (look/assert paths confined, but no systematic audit yet); symlink-escape canonicalisation in `check_path` (lexical only).
- `deploy/Dockerfile` + `deploy/docker-compose.yml` — no `deploy/` dir exists yet.
- Closer duties: gap analysis of this report, `test_integration_tc_b.py`, arch diagram updates (component-overview verify block, api-contracts Phase-2, data-model SNAPSHOT/RECORD/EVIDENCE rows if missing, flow-agent-edit-verify), requirements-matrix + coverage-map rows for SW-REQ-GW-VERIFY, SYS3 smoke.

**Run tests**: `python3 -m pytest gateway/tests/ -q` from repo root (Crafters dir).

---

## ⚠️ Known Issues / Limitations (if any)

- No pilot CLI binaries installed → `BackendManager(use_fake=True)` auto-fallback active; `engine.restore` rollback unexercised (fakes lack it) — re-verify against real `<app>-cli mcp` when available.
- Visual asserts are coarse on fakes (revision-equality proxy, not pixel diff) — real diff needs renderer-backed backends.
- `check_path` is lexical (no filesystem canonicalisation) — symlink escapes are TC-B-02's hardening scope.
- Snapshot data_ref is `{revision}` only — real-CLI file re-open mechanics deferred to TC-B-02/containers.
- No coverage-percentage tooling; test counts (96) are the baseline.

---

## Traceability

| Level | ID | Artifact |
|-------|-----|---------|
| SYS1 | SYS1-001 | Epic: EPIC_001_CRAFTER_GATEWAY.md |
| SWE1 | SWE1-B | TC: TC-B-00_COMPONENT_DEFINITION.md |
| SWE3 | SWE3-B-01 | Issue: TC-B-01_VERIFY_TOOLS.md |
| SWE4 | test_phase2 | Tests: `gateway/tests/test_phase2.py` (29) |

---

## Self-verification (no-reviews mode)

Gate table (STEP D1–D5, all from repo root):

| Gate | Command | Exit | Result |
|------|---------|------|--------|
| D1 Lint | `python3 -m ruff check gateway/` + `ruff format --check gateway/` | 0 | 0 errors, 15 files formatted |
| D2 Typecheck/build | `python3 -m compileall -q gateway` | 0 | 0 errors |
| D3 Tests (issue + module suite) | `python3 -m pytest gateway/tests/ -q` | 0 | 96 passed (67 unit + 29 new), 0 failed; baseline 67 → no regressions |
| D4 Smoke through wiring | in-memory `Client` over `create_gateway()+register_phase1+phase2` → snapshot→run→look→assert→record | 0 | All 10 tools reachable; snapshot rev 1 → run rev 2 → look hash → assert pass → record rec_id |
| D5 Self-checklist | every file maps to a requirement; every requirement has impl + test; callers verified (all new symbols; Phase-1 hook re-verified via existing suite); no suppression; no secrets in logs (tested); all issue boxes ticked | — | yes to all |

Requirement → `file:line` → test → status:

| Requirement | Implementation | Test | Status |
|-------------|----------------|------|--------|
| `craft_look` (scope/index/region/max_side/detail) | `gateway/tools_phase2.py` (`craft_look`) | `test_look_scopes/details/region_and_clamp` | ✅ |
| `craft_snapshot`/`craft_restore` (token + revision) | `gateway/tools_phase2.py` + `gateway/snapshots.py` (`SnapshotStore`) | `test_snapshot_restore_round_trip`, store isolation test | ✅ |
| `craft_record` (reject measured-without-evidence) | `gateway/tools_phase2.py` (`craft_record`) | `test_record_rejects_unbacked_measured_claim` | ✅ |
| `craft_assert` (structural default, visual opt-in) | `gateway/tools_phase2.py` (`craft_assert`) | structural/visual/tolerance tests | ✅ |
| Auto-snapshot hook (destructive batches + app.save) | `gateway/tools_phase1.py` (`_maybe_auto_snapshot`) + `snapshots.is_destructive_command` | predicate + hook tests | ✅ |
| Wire into `main.py` alongside Phase-1 | `gateway/main.py` (shared store) | `test_register_phase2_tools_wires_all_five` + smoke | ✅ |
| Logger (hash/id refs, redaction) | egress + snapshot/record/assert events | redaction test | ✅ |

Wiring chain proof: `python -m gateway.main` entry → `create_gateway()` + both `register_*` with shared `SnapshotStore` → in-memory MCP client lists 10 tools → `craft_snapshot` rev 1 → `craft_run` rev 2 → `craft_look` hash `sha256:fake` → `craft_assert` pass → `craft_record` rec id. Observable effect verified through the real FastMCP path.

Residual risks / limitations / open questions:

- Real-CLI paths (proxy + `engine.restore` rollback) unexercised — no pilot CLIs installed.
- Visual asserts coarse on fakes; real pixel-diff needs renderer-backed backends.
- `check_path` lexical only — symlink hardening is TC-B-02 scope.
- Coverage % tooling has no target; counts are the baseline.

Independent review intentionally omitted — TC-B is declared `no-reviews`; gap analysis is inherited by the TC closer (TC-B-02).

## Lane 5 audit (2026-10-12) — executed evidence

- Re-ran `python3 -m pytest gateway/tests/ -q` → **188 passed, 9 skipped** (9 skipped = real-CLI tests: no binaries; incl. 29 Phase-2 SWE4 green).
- Live in-memory gateway: 12 tools reachable; `craft_status` → fake mode; no `*-cli` on PATH.
- Gate verdict: verify-tool mechanics + fake-mode asserts backed ✅; `engine.restore` rollback + real pixel-diff NOT backed (fakes lack `engine.restore`; visual asserts are revision-equality proxies).
- TODO (unbacked by real run): (1) `engine.restore` rollback against real CLIs; (2) renderer-backed pixel-diff for visual asserts.
