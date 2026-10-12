# TC-C-00: Accessibility Refs — Component Definition

> **Epic**: E-001 Crafter Gateway (`../EPIC_001_CRAFTER_GATEWAY.md`)
> **V-Model**: SWE1-C (derived from SYS1-001)
> **Requirements**: SW-REQ-A11Y
> **Review Mode**: no-reviews (impl self-verifies per STEP E-NR; no reviewer is spawned)
> **Status**: ✅ Complete (TC-C-01 ✅, TC-C-02 ✅)
> **Last Updated**: 2026-10-12

---

## Component Goal

Reference upstream contributions making 2 pilot apps 100% agent-accessible (pdfcraft:
AccessKit-via-MCP; photocraft: canvasRect synthesis), plus a documented contribution pattern so
the remaining 10 apps can follow without new design work. This is Part A of the discovery brief.

## Responsibilities

1. **pdfcraft AccessKit-via-MCP** — expose the existing AccessKit widget tree through the MCP
   server (today it is control-channel only).
2. **photocraft canvasRect synthesis** — provide document↔screen mapping despite `ui.pointer`
   being document-space with no canvas rect reported.
3. **Contribution pattern doc** — repeatable PR shape for the other 10 apps (rollout deferred).

## Logging & Observability Allocation (mandatory cross-cutting)

Upstream PRs must not introduce private logging; gateway-side synthesis uses the project logger.
TC-C-01 instruments; TC-C-02 (closer) verifies no secret/PII paths and documents N/A where the
upstream code has no runtime event surface.

## Integration Points

| Direction | Component | Interface |
|:----------|:----------|:----------|
| **Uses** | TC-A/B gateway | Synthesis hooks, session/roots |
| **Uses** | Upstream Craft repos | PRs against pdfcraft + photocraft |
| **Provides to** | Gateway perception | AccessKit + canvasRect sources |
| **Provides to** | Maintainers | Contribution pattern doc |

## Runtime Instantiation Map

| Component Class | Instantiated In | Lifecycle Owner | Route / Tool / Export Path |
|:----------------|:----------------|:----------------|:---------------------------|
| AccessKit bridge (pdfcraft) | upstream PR / gateway shim | app / gateway | MCP tool via gateway |
| canvasRect synthesis (photocraft) | `gateway/perception.py` | gateway session | `query_map` backing data |

> Rules: TC-C-01 owns the two reference implementations; TC-C-02 owns the pattern doc and
> verifies rows.

## Architecture References

| Artifact | Path | Relevance |
|----------|------|-----------|
| Component Overview | `project_management/architecture/diagrams/component-overview.md` | A11y refs block |
| API Contracts | `project_management/architecture/diagrams/api-contracts.md` | Perception additions |
| Research | `project_management/_templates/raw_Repository_findings/06-PERCEPTION.md` | Gaps being closed |

## Key Files

| Action | File | Purpose |
|:-------|:-----|:--------|
| Create | `gateway/perception.py` | canvasRect synthesis + AccessKit proxy |
| Create | `docs/a11y-contribution-pattern.md` | Repeatable upstream PR shape |
| Create | `gateway/tests/test_perception.py` | SWE4 unit tests |

## Issues

| Issue | Title | Type | V-Model | Priority | Effort | Status |
|:------|:------|:-----|:--------|:---------|:-------|:-------|
| [TC-C-01](TC-C-01_A11Y_REFERENCES.md) | pdfcraft AccessKit + photocraft canvasRect | 🔨 Impl | SWE3-C-01 | P1-High | M | ✅ Complete |
| [TC-C-02](TC-C-02_PATTERN_AND_CLOSER.md) | Contribution pattern + TC closer | 🔨 Impl | SWE3-C-02 | P1-High | S | ✅ Complete |

## Acceptance Test Plan (SWE6)

| # | Acceptance Criterion | Test Type | Gate |
|---|---------------------|-----------|------|
| 1 | AccessKit widget tree reachable via gateway MCP tool | Integration | 🔴 |
| 2 | Document↔screen mapping resolves for photocraft view | Unit + Integration | 🔴 |
| 3 | Pattern doc lets a third app be scoped without new design | Review (closer) | 🟡 |

## Decisions Log

| Date | Decision | Rationale | ADR |
|:-----|:---------|:----------|:----|
| 2026-10-11 | 2-app reference scope; 10-app rollout deferred | Discovery A1; size cap | — |

| 2026-10-12 | Pattern doc with Shape W/M + decision tree + gridcraft scoping; gateway shim is primary, PRs remove it (TC-C-02) | Rollout needs no new design | — |

## Architecture Documentation Revisions

| Date | Issue | Changes Made |
|------|-------|-------------|
| 2026-10-12 | TC-C-02 | component-overview (a11y block), api-contracts (perception rows), requirements-matrix + coverage-map SW-REQ-A11Y → ✅ |

---

*Shared context document — read before starting any TC-C issue, update after completing each one.*
