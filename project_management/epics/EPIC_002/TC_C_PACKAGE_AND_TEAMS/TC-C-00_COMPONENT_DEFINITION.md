# TC-C-00: Package + Teams — Component Definition

> **Epic**: E-002 Crafter Chat UI (`../EPIC_002_CRAFTER_CHAT_UI.md`)
> **V-Model**: SWE1-C (derived from SYS1-002)
> **Requirements**: SW-REQ-PACK
> **Review Mode**: no-reviews (impl self-verifies per STEP E-NR; no reviewer is spawned)
> **Status**: ✅ Complete
> **Last Updated**: 2026-10-12

---

## Component Goal

Docker-packaged local run (gateway + view + pilot CLIs, fresh-checkout working) and Scaico team
select driving agents end-to-end. This is the shippable slice: install, connect, chat, verify.

## Responsibilities

1. **Packaging** — Docker compose for gateway + view (+ pilot CLIs), fresh-checkout run docs.
2. **Scaico teams e2e** — team select from `craft_*` team JSONs, agents drive pilot apps via
   gateway, mailto fallback path verified.
3. **Epic boundary** — TC-C-02 closes the TC and EPIC_002.

## Logging & Observability Allocation (mandatory cross-cutting)

Compose-level logging via project logger; no secrets in container logs. TC-C-01 instruments;
TC-C-02 (closer) verifies and documents N/A where packaging has no runtime event surface.

## Integration Points

| Direction | Component | Interface |
|:----------|:----------|:----------|
| **Uses** | EPIC_001 gateway + Docker pattern | `deploy/` reuse |
| **Uses** | TC-A/B chat + settings | Packaged services |
| **Uses** | Scaico API + team JSONs | Team select + agent runs |
| **Provides to** | Operators | Runnable local app |

## Runtime Instantiation Map

| Component Class | Instantiated In | Lifecycle Owner | Route / Tool / Export Path |
|:----------------|:----------------|:----------------|:---------------------------|
| Compose stack | `deploy/docker-compose.yml` | operator (`docker compose up`) | view :port + gateway :port |
| Team select | Settings view (TC-B) | user | Scaico team list → agent session |

> Rules: TC-C-01 owns packaging; TC-C-02 owns teams e2e + epic boundary and verifies rows.

## Architecture References

| Artifact | Path | Relevance |
|----------|------|-----------|
| Component Overview | `project_management/architecture/diagrams/component-overview.md` | Full stack |
| API Contracts | `project_management/architecture/diagrams/api-contracts.md` | Team + packaging contracts |

## Key Files

| Action | File | Purpose |
|:-------|:-----|:--------|
| Create | `deploy/docker-compose.yml` | Full-stack local run |
| Create | `deploy/README.md` | Fresh-checkout run docs |
| Create | Team e2e tests | Scaico team select + agent run |

## Issues

| Issue | Title | Type | V-Model | Priority | Effort | Status |
|:------|:------|:-----|:--------|:---------|:-------|:-------|
| [TC-C-01](TC-C-01_PACKAGING.md) | Docker packaging + fresh-checkout run | 🔨 Impl | SWE3-C-01 | P1-High | M | ✅ Complete |
| [TC-C-02](TC-C-02_TEAMS_E2E_AND_CLOSER.md) | Scaico teams e2e + epic closer | 🔨 Impl | SWE3-C-02 | P1-High | S | ✅ Complete |

## Acceptance Test Plan (SWE6)

| # | Acceptance Criterion | Test Type | Gate |
|---|---------------------|-----------|------|
| 1 | Fresh checkout → compose up → chat loads | System | 🔴 |
| 2 | Team select → agent edits pilot doc with verify actions | Integration | 🔴 |
| 3 | No key → mailto CTA visible; direct mode works | Unit + Integration | 🔴 |

## Decisions Log

| Date | Decision | Rationale | ADR |
|:-----|:---------|:----------|:----|
| 2026-10-11 | Web + Docker first; Electron deferred | Discovery D1; size cap | — |

## Architecture Documentation Revisions

| Date | Issue | Changes Made |
|------|-------|-------------|
| — | — | (filled by TC-C-02 closer) |

---

*Shared context document — read before starting any TC-C issue, update after completing each one.*
