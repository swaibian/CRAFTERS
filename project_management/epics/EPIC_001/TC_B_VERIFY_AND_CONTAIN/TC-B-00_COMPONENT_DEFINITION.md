# TC-B-00: Verify + Contain — Component Definition

> **Epic**: E-001 Crafter Gateway (`../EPIC_001_CRAFTER_GATEWAY.md`)
> **V-Model**: SWE1-B (derived from SYS1-001)
> **Requirements**: SW-REQ-GW-VERIFY
> **Review Mode**: no-reviews (impl self-verifies per STEP E-NR; no reviewer is spawned)
> **Status**: ✅ Complete (TC-B-01 ✅, TC-B-02 ✅)
> **Last Updated**: 2026-10-11

---

## Component Goal

Phase 2 verification tools (`craft_look`, `craft_snapshot`/`craft_restore`, `craft_record`,
`craft_assert`) plus containment hardening (per-session roots enforcement, containerised local
run). This is where the agent stops being able to lie about what it did — every claim needs
evidence, every destructive edit needs a snapshot.

## Responsibilities

1. **Verification tools** — look (unified render), snapshot/restore (seatbelt), record
   (evidence-backed claims), assert (structural/visual postconditions).
2. **Containment** — enforce per-session roots on all file paths; Docker packaging for local run.
3. **Trust wiring** — auto-snapshot policy before destructive batches; reject unbacked
   "measured" claims.

## Logging & Observability Allocation (mandatory cross-cutting)

Instrument verification tool calls, snapshot/restore events, assert pass/fail, record validations
through the project logger. TC-B-01 instruments; TC-B-02 (closer) verifies redaction (renders
referenced by hash/id, never embedded) and audit/metrics separation.

## Integration Points

| Direction | Component | Interface |
|:----------|:----------|:----------|
| **Uses** | TC-A Gateway Core | Phase-1 tools, session/roots, auth |
| **Provides to** | EPIC_002 Chat UI | look/snapshot/assert/record for verify actions |
| **Provides to** | Agents | Trust primitives (seatbelt + evidence) |

## Runtime Instantiation Map

| Component Class | Instantiated In | Lifecycle Owner | Route / Tool / Export Path |
|:----------------|:----------------|:----------------|:---------------------------|
| Phase-2 tools | `gateway/tools_phase2.py` | `CrafterGateway` (TC-A) | FastMCP tools: look/snapshot/restore/record/assert |
| `SnapshotStore` | `gateway/snapshots.py` | session lifecycle | session asset store |
| Container image | `deploy/Dockerfile` + compose | operator | local run |

> Rules: TC-B-01 owns verification tools; TC-B-02 owns containment + Docker and verifies rows.

## Architecture References

| Artifact | Path | Relevance |
|----------|------|-----------|
| Component Overview | `project_management/architecture/diagrams/component-overview.md` | Verify block |
| Data Model | `project_management/architecture/diagrams/data-model.md` | SNAPSHOT, RECORD, EVIDENCE |
| API Contracts | `project_management/architecture/diagrams/api-contracts.md` | Phase-2 sequences |
| Flows | `project_management/architecture/diagrams/flow-agent-edit-verify.md` | Snapshot→act→look→assert→record |

## Key Files

| Action | File | Purpose |
|:-------|:-----|:--------|
| Create | `gateway/tools_phase2.py` | look/snapshot/restore/record/assert |
| Create | `gateway/snapshots.py` | Snapshot store |
| Create | `gateway/tests/test_phase2.py` | SWE4 unit tests |
| Create | `deploy/Dockerfile`, `deploy/docker-compose.yml` | Containerised local run |

## Issues

| Issue | Title | Type | V-Model | Priority | Effort | Status |
|:------|:------|:-----|:--------|:---------|:-------|:-------|
| [TC-B-01](TC-B-01_VERIFY_TOOLS.md) | Verification tools (look/snapshot/record/assert) | 🔨 Impl | SWE3-B-01 | P0-Critical | M | ✅ Complete |
| [TC-B-02](TC-B-02_CONTAINMENT_AND_CLOSER.md) | Containment + Docker + TC closer | 🔨 Impl | SWE3-B-02 | P0-Critical | M | ✅ Complete |

## Acceptance Test Plan (SWE6)

| # | Acceptance Criterion | Test Type | Gate |
|---|---------------------|-----------|------|
| 1 | `craft_record` with confidence measured + empty evidence is rejected | Unit | 🔴 |
| 2 | Snapshot → destructive edit → restore returns prior revision | Integration | 🔴 |
| 3 | Path outside session roots is rejected on every file tool | Unit + Integration | 🔴 |

## Decisions Log

| Date | Decision | Rationale | ADR |
|:-----|:---------|:----------|:----|
| 2026-10-11 | Structural asserts default; visual opt-in with tolerance | Pixel asserts flake across renderers | — |
| 2026-10-11 | One shared SnapshotStore across Phase-1 hook + Phase-2 tools (TC-B-01) | Auto-snapshot tokens must be restorable; separate stores would orphan them | — |
| 2026-10-11 | craft_look returns metadata + hash only, never pixels (TC-B-01) | Gateway never carries image bytes; hash enables caching/diffing | — |

| 2026-10-11 | Token bootstrap (`CRAFTER_DEV_TOKEN` loopback-only, tokens-file JSON) + `--work-dir` default roots (TC-B-02) | Gateway startable from bare checkout; empty store stays fail-closed | — |
| 2026-10-11 | Deny-by-default on dangling-outside symlinks; `.` allowed as root (TC-B-02) | Tested in `test_containment.py` | — |

## Architecture Documentation Revisions

| Date | Issue | Changes Made |
|------|-------|-------------|
| 2026-10-11 | TC-B-02 | component-overview (TC-B blocks), api-contracts (Phase-2 + containment + local-run), requirements-matrix + coverage-map SW-REQ-GW-VERIFY → ✅ |

---

*Shared context document — read before starting any TC-B issue, update after completing each one.*
