# TC-A-01: Gateway Service + Auth + Allowlists

**Component**: Gateway Core
**Epic**: E-001 Crafter Gateway
**V-Model**: SWE3-A-01
**Type**: 🔨 IMPLEMENTATION
**Priority**: P0-Critical
**Estimated Effort**: M
**Dependencies**: none (first issue in TC)
**SW-REQ**: SW-REQ-GW-CORE

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

Stand up the FastMCP gateway process with both transports and server-enforced auth, so every
later tool has a trustworthy surface to attach to. If auth/allowlist enforcement is wrong, every
downstream issue inherits an auth bypass.

**High Stakes**: Bearer-token bypass would expose all 12 Craft apps to any holder.
**Constraints**: No tokens, secrets, document content, or image data in logs; per-user denial.

---

## 🏗️ Architectural Context

```
Agent (stdio | HTTPS) → gateway/main.py → gateway/auth.py → (tools attach in TC-A-02)
                                   → gateway/backends.py → <app>-cli mcp (stdio)
```

See: `project_management/architecture/README.md` for full context.

---

## Traceability

| Level | ID | Artifact |
|-------|-----|---------|
| SYS1 | SYS1-001 | Epic: EPIC_001_CRAFTER_GATEWAY.md |
| SWE1 | SWE1-A | TC: TC-A-00_COMPONENT_DEFINITION.md |
| SWE3 | SWE3-A-01 | This issue |
| SWE4 | — | Unit tests in: `gateway/tests/test_auth.py`, `gateway/tests/test_backends.py` |

---

## 📋 Task List

### 0.0 Read Architecture Documentation [MANDATORY]

- [x] **Read: `project_management/architecture/README.md`**
- [x] **Read: relevant diagrams** in `project_management/architecture/diagrams/`
  (component-overview, api-contracts)

### 0.1 Read Predecessor Context [MANDATORY]

- [x] **Read: `TC-A-00_COMPONENT_DEFINITION.md`**

### 0.2 Run Full Test Suite [MANDATORY GATE 🔴]

- [x] Detect project test runner (new `gateway/` package: pytest expected)
- [x] **Run typecheck** (pyright/mypy as configured) [MANDATORY GATE 🔴]
- [x] **Run linter** (ruff as configured) [ADVISORY 🟢 on TC-X-01]
- [x] Record baseline: total tests, passing, failing, skipped, coverage %, typecheck errors, lint errors
- [x] **Gate**: If new test failures OR new typecheck errors vs. known baseline, STOP and investigate.

### 0.3 Tooling Gate (TC-X-01 criterion)

- [x] typecheck + tests + lint clean before handoff to TC-A-02.

### 1. Investigate Requirements

- [x] Read: `project_management/_templates/raw_Repository_findings/08-REQUIRED-TOOLS.md` §F (transport)
- [x] Read: swaibian-one `src/mcp/main.py` (auth + catalog pattern, reference only)
- [x] Read: swaibian-one `src/controller/api_key_auth.py`, `mcp_auth.py` (reference only)

### 1.5 Logging & Observability Integration [MANDATORY CROSS-CUTTING]

- [x] Instrument gateway ingress (tool call, user/session context), CLI spawn/proxy events,
  auth allow/deny decisions through the project logger.
- [x] Redact: tokens, secrets, raw bodies, document content, image data. Allow-list safe fields.
- [x] Keep operational logs separate from security-audit records and metrics.

### 2. Write/Update Requirements

- [x] Record SW-REQ-GW-CORE auth/transport requirements in code-adjacent docs.

### 3. Investigate Architecture

- [x] Review: FastMCP stdio + streamable_http serving; bearer extraction; per-session roots model.

### 4. Implement Code

- [x] `gateway/main.py`: FastMCP app, stdio + streamable_http lifespan, wire into process entrypoint.
- [x] `gateway/auth.py`: bearer validation, per-token tool allowlists, per-user denial.
- [x] `gateway/backends.py`: spawn `<app>-cli mcp` subprocesses, proxy JSON-RPC, session roots.
- [x] Session registry: session id → roots, tokens, app backends.

### 5. Create Unit Tests (SWE4) [MANDATORY]

- [x] `gateway/tests/test_auth.py`: valid/invalid/expired bearer; allowlist allow/deny per tool;
  per-user denial; no token leakage in errors/logs.
- [x] `gateway/tests/test_backends.py`: spawn/proxy with fake CLI; session isolation (roots do
  not cross sessions); failure paths.
- [x] Logger tests: event schema, context propagation, redaction (forbidden-field cases).

### 6. Run Full Test Suite + Coverage [MANDATORY GATE 🔴]

- [x] Execute test runner (all scopes)
- [x] **Run typecheck** — 0 new errors vs. Task 0.2 baseline [MANDATORY GATE 🔴]
- [x] **Run linter** — record vs. baseline [ADVISORY on TC-X-01]
- [x] Record: total tests, passing, failing, skipped, coverage %, typecheck errors, lint errors
- [x] **Gate**: 0 new failures allowed. Coverage must not regress. Typecheck must not regress.

### 7. Create Documentation

- [x] Inline docs for new/changed APIs; auth contract doc for TC-A-02 consumer.
- [x] Note for closer: transport + auth rows for api-contracts diagram.

### 8. Write Completion Report & Handoff [MANDATORY]

- [x] Complete `TC-A-01_COMPLETION_REPORT.md`
- [x] **Write handoff section for TC-A-02 team** — MUST include:
  - What was built: files created/modified, APIs exposed, schemas changed
  - Key decisions made and why (especially deviations from this plan)
  - Known limitations or edge cases
  - Open risks or questions for the next team
  - Code examples showing how to use what was built
  - Gate results table
- [x] Update `TC-A-00_COMPONENT_DEFINITION.md` with status + new decisions

---

## ⚠️ Constraints

- No token/secret/PII in logs or error messages (tested).
- Reuse swaibian-one by reference only — do NOT modify swaibian-one code.

---

## 📁 Files to Modify

| Action | File Path | Description |
|--------|-----------|-------------|
| Create | `gateway/main.py` | FastMCP app + transports + entrypoint wiring |
| Create | `gateway/auth.py` | Bearer + allowlist enforcement |
| Create | `gateway/backends.py` | App CLI spawn/proxy + session roots |
| Create | `gateway/tests/test_auth.py` | Auth unit tests |
| Create | `gateway/tests/test_backends.py` | Backend unit tests |
| Read   | `project_management/_templates/raw_Repository_findings/08-REQUIRED-TOOLS.md` | Phase 1+2 tool spec |

---

## ✅ Acceptance Criteria

- [x] Gateway serves stdio + streamable_http; bearer enforced; allowlist denies unlisted tools.
- [x] Session isolation: roots/tokens do not leak across sessions (tested).
- [x] All unit tests passing (SWE4).
- [x] Coverage not regressed from Task 0.2 baseline.
- [x] Completion report written with handoff for TC-A-02.
- [x] TC-A-00 updated with status and decisions.
- [x] Logger evidence included: event names/fields, request/user context path, redaction tests,
  audit/metrics separation.

---

## 📖 Reference Documents

- V-Model Framework: `project_management/_templates/V_MODEL_FRAMEWORK.md`
- Architecture: `project_management/architecture/README.md`
- Epic: `project_management/epics/EPIC_001_CRAFTER_GATEWAY.md`
- Component: `project_management/epics/EPIC_001/TC_A_GATEWAY_CORE/TC-A-00_COMPONENT_DEFINITION.md`
- SW Requirements: SW-REQ-GW-CORE (see TC-A-00)
- Research: `project_management/_templates/raw_Repository_findings/08-REQUIRED-TOOLS.md`

---

## 🔗 Related Issues

- Depends On: none (first issue)
- Blocks: TC-A-02 (Phase-1 tools + pilot wiring + closer)
- Related: EPIC_002 chat UI (consumer of this gateway)

---

## Gate Results (filled during execution)

| Gate | Level | Result | Notes |
|------|-------|--------|-------|
| Pre-check test suite (Task 0.2) | SWE4 | ✅ baseline: 0 tests (greenfield, no gateway/ yet) | |
| Post-implementation suite (Task 6) | SWE4 | ✅ 47 passed, 0 failed | |
| Coverage vs baseline | SWE4 | ✅ N/A greenfield, all new code tested | |
| Coverage vs target | ADVISORY | ✅ 47 tests cover auth/backends/logger | |
