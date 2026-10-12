# TC-A-00: Gateway Core — Component Definition

> **Epic**: E-001 Crafter Gateway (`../EPIC_001_CRAFTER_GATEWAY.md`)
> **V-Model**: SWE1-A (derived from SYS1-001)
> **Requirements**: SW-REQ-GW-CORE
> **Review Mode**: no-reviews (impl self-verifies per STEP E-NR; no reviewer is spawned)
> **Status**: ✅ Complete
> **Last Updated**: 2026-10-11

---

## Component Goal

A Python FastMCP gateway service exposing Phase 1 tools (`craft_apps`, `craft_status`,
`craft_run`, `craft_run_tool`, `craft_app_call`) over stdio + streamable_http with bearer-token
auth and per-token tool allowlists, fronting the pilot app CLIs (photocraft, pdfcraft,
gridcraft). This is the foundation every other component builds on.

## Responsibilities

1. **FastMCP service + transports** — stdio for local agents; streamable_http with bearer
   tokens for Scaico teams.
2. **Auth + allowlists** — per-token tool allowlists enforced server-side; per-session
   filesystem roots plumbed through.
3. **Pilot app wiring** — spawn and proxy `<app>-cli mcp` for photocraft, pdfcraft, gridcraft;
   generic so the other 9 light up without code changes.

## Logging & Observability Allocation (mandatory cross-cutting)

Gateway uses the project logger at runtime boundaries (tool call ingress, app CLI spawn/proxy,
auth decisions); no private logging setup. TC-A-01 instruments boundaries; TC-A-02 (closer)
verifies wiring, redaction (no tokens, no document content, no image data in logs), and audit/
metrics separation. Reference: swaibian-one `src/mcp/main.py` logger usage by analogy.

## Integration Points

| Direction | Component | Interface |
|:----------|:----------|:----------|
| **Uses** | Craft app CLIs | stdio MCP (`<app>-cli mcp`) |
| **Uses** | swaibian-one auth patterns | `api_key_auth` / `mcp_auth` (reference only) |
| **Provides to** | TC-B verification tools | Gateway tool surface + session/roots |
| **Provides to** | EPIC_002 Chat UI | streamable_http endpoint + tool catalog |

## Runtime Instantiation Map

| Component Class | Instantiated In | Lifecycle Owner | Route / Tool / Export Path |
|:----------------|:----------------|:----------------|:---------------------------|
| `CrafterGateway` (FastMCP app) | `gateway/main.py` | process supervisor / Docker entrypoint | stdio + `POST /mcp` (streamable_http) |
| `AppBackend` (per-app proxy) | `gateway/backends.py` | `CrafterGateway` lifespan | internal; one per pilot app |
| `AuthAllowlist` | `gateway/auth.py` | request middleware | `Authorization: Bearer` header |

> Rules: TC-A-01 owns "wire into `gateway/main.py`" explicitly. TC-A-02 verifies every row.

## Architecture References

| Artifact | Path | Relevance |
|----------|------|-----------|
| Component Overview | `project_management/architecture/diagrams/component-overview.md` | Gateway + tools block |
| Data Model | `project_management/architecture/diagrams/data-model.md` | SESSION, TOKEN, ALLOWLIST, ROOT |
| API Contracts | `project_management/architecture/diagrams/api-contracts.md` | Phase-1 tool contracts |
| Logging & Observability | swaibian-one `src/mcp/main.py` (reference) | Boundary logging pattern |

## Key Files

| Action | File | Purpose |
|:-------|:-----|:--------|
| Create | `gateway/main.py` | FastMCP app, transports, lifespan |
| Create | `gateway/auth.py` | Bearer + allowlist enforcement |
| Create | `gateway/backends.py` | App CLI spawn/proxy, session roots |
| Create | `gateway/tools_phase1.py` | craft_apps/status/run/run_tool/app_call |
| Create | `gateway/tests/test_phase1.py` | SWE4 unit tests |

## Issues

| Issue | Title | Type | V-Model | Priority | Effort | Status |
|:------|:------|:-----|:--------|:---------|:-------|:-------|
| [TC-A-01](TC-A-01_GATEWAY_SERVICE_AND_AUTH.md) | Gateway service + auth + allowlists | 🔨 Impl | SWE3-A-01 | P0-Critical | M | ✅ Complete |
| [TC-A-02](TC-A-02_PHASE1_TOOLS_AND_CLOSER.md) | Phase-1 tools + pilot wiring + TC closer | 🔨 Impl | SWE3-A-02 | P0-Critical | M | ✅ Complete |

## Acceptance Test Plan (SWE6)

| # | Acceptance Criterion | Test Type | Gate |
|---|---------------------|-----------|------|
| 1 | `craft_status` lists pilot apps with documents/jobs via proxied CLIs | Integration | 🔴 |
| 2 | Bearer token without allowlist entry is denied the tool | Unit + Integration | 🔴 |
| 3 | Session roots confine file tools; escape rejected | Unit + Integration | 🔴 |

## Decisions Log

| Date | Decision | Rationale | ADR |
|:-----|:---------|:----------|:----|
| 2026-10-11 | Python FastMCP, stdio + streamable_http | Discovery B1; mirrors swaibian-one | — |
| 2026-10-11 | Auth as FastMCP Middleware; stdio token via `_gateway_token` arg (stripped pre-dispatch) | No header surface on stdio; server-side enforcement on every call | — |
| 2026-10-11 | BackendManager auto-fallback to FakeAppBackend when no CLI on PATH; backends shared per app, isolation in session roots | Pilot CLIs absent; keeps gateway/tools/tests end-to-end working | — |
| 2026-10-11 | TC-A-01 complete: 47 tests pass, ruff clean, smoke via entrypoint+Client+http_app | — | — |
| 2026-10-11 | Phase-1 tools wired; gap fix (no redaction on forwarded params); TC-A complete: 67 tests, SYS3 smoke stdio+http | — | — |

## Architecture Documentation Revisions

| Date | Issue | Changes Made |
|------|-------|-------------|
| 2026-10-11 | TC-A-02 | Gateway block → real files; Phase-1 sequences + transport/auth/tool contracts; matrix + coverage-map SW-REQ-GW-CORE rows ✅ |

---

*Shared context document — read before starting any TC-A issue, update after completing each one.*
