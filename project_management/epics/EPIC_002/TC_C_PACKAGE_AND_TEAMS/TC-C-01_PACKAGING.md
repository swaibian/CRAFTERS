# TC-C-01: Docker Packaging + Fresh-Checkout Run

**Component**: Package + Teams
**Epic**: E-002 Crafter Chat UI
**V-Model**: SWE3-C-01
**Type**: 🔨 IMPLEMENTATION
**Priority**: P1-High
**Estimated Effort**: M
**Dependencies**: TC-B-02 (Settings + closer)
**SW-REQ**: SW-REQ-PACK

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

Package gateway + view (+ pilot CLIs) as a Docker compose stack that runs from a fresh
checkout with documented prereqs. If it doesn't run fresh, it doesn't ship.

**High Stakes**: Unrunnable packaging blocks all evaluation.
**Constraints**: Fresh-checkout run; documented prereqs; no secrets baked into images.

---

## 🏗️ Architectural Context

```
docker compose up → gateway + view + pilot CLIs → chat loads → settings → run
```

See: `project_management/architecture/README.md` for full context.

---

## Traceability

| Level | ID | Artifact |
|-------|-----|---------|
| SYS1 | SYS1-002 | Epic: EPIC_002_CRAFTER_CHAT_UI.md |
| SWE1 | SWE1-C | TC: TC-C-00_COMPONENT_DEFINITION.md |
| SWE3 | SWE3-C-01 | This issue |
| SWE4 | — | Unit tests in: compose validation + config tests |

---

## 📋 Task List

### 0.0 Read Architecture Documentation [MANDATORY]

- [ ] **Read: `project_management/architecture/README.md`**
- [ ] **Read: relevant diagrams** in `project_management/architecture/diagrams/`

### 0.1 Read Predecessor Context [MANDATORY]

- [ ] **Read: `TC-C-00_COMPONENT_DEFINITION.md`**
- [ ] **Read: `TC-B-02_COMPLETION_REPORT.md`** ← settings + stream handoff

### 0.2 Run Full Test Suite [MANDATORY GATE 🔴]

- [ ] Test runner + typecheck + lint (MANDATORY); baseline; Gate: 0 new issues.

### 0.3 Tooling Gate (TC-X-01 criterion)

- [ ] typecheck + tests + lint clean before handoff to TC-C-02.

### 1. Investigate Requirements

- [ ] Read: EPIC_001 TC-B-02 Docker pattern (reuse); swaibian-one `deploy/` (reference).

### 1.5 Logging & Observability Integration [MANDATORY CROSS-CUTTING]

- [ ] Compose logging via project logger; no secrets in container logs (tested).

### 2. Write/Update Requirements

- [ ] Record packaging + run contracts.

### 3. Investigate Architecture

- [ ] Review: services, ports, volumes (work dir mount), env config.

### 4. Implement Code

- [ ] `deploy/docker-compose.yml`: gateway + view + pilot CLIs; work-dir volume; env template.
- [ ] `deploy/README.md`: prereqs, fresh-checkout run, troubleshooting.

### 5. Create Unit Tests (SWE4) [MANDATORY]

- [ ] Compose validation; config tests; log-redaction tests.

### 6. Run Full Test Suite + Coverage [MANDATORY GATE 🔴]

- [ ] Runner + typecheck + lint 0 new errors; coverage not regressed.

### 7. Create Documentation

- [ ] Run docs; note for closer.

### 8. Write Completion Report & Handoff [MANDATORY]

- [ ] Complete `TC-C-01_COMPLETION_REPORT.md`
- [ ] **Write handoff section for TC-C-02 team** — MUST include: what was built, decisions +
  deviations, limitations/edge cases, open risks, usage examples, gate results.
- [ ] Update `TC-C-00_COMPONENT_DEFINITION.md` with status + new decisions

---

## ⚠️ Constraints

- No secrets in images or logs; fresh-checkout run required.

---

## 📁 Files to Modify

| Action | File Path | Description |
|--------|-----------|-------------|
| Create | `deploy/docker-compose.yml` | Full-stack local run |
| Create | `deploy/README.md` | Run docs |
| Create | Packaging tests | Compose/config validation |

---

## ✅ Acceptance Criteria

- [ ] Fresh checkout → compose up → chat loads (documented).
- [ ] All unit tests passing; coverage not regressed.
- [ ] Completion report with handoff for TC-C-02; TC-C-00 updated.
- [ ] Logger evidence included.

---

## 📖 Reference Documents

- V-Model Framework: `project_management/_templates/V_MODEL_FRAMEWORK.md`
- Architecture: `project_management/architecture/README.md`
- Epic: `project_management/epics/EPIC_002_CRAFTER_CHAT_UI.md`
- Component: `project_management/epics/EPIC_002/TC_C_PACKAGE_AND_TEAMS/TC-C-00_COMPONENT_DEFINITION.md`
- Predecessor Report: `project_management/epics/EPIC_002/TC_B_STREAM_AND_SETTINGS/TC-B-02_COMPLETION_REPORT.md`
- SW Requirements: SW-REQ-PACK (see TC-C-00)

---

## 🔗 Related Issues

- Depends On: TC-B-02
- Blocks: TC-C-02 (Teams e2e + closer)

---

## Gate Results (filled during execution)

| Gate | Level | Result | Notes |
|------|-------|--------|-------|
| Pre-check test suite (Task 0.2) | SWE4 | ⬜ PENDING | |
| Post-implementation suite (Task 6) | SWE4 | ⬜ PENDING | |
| Coverage vs baseline | SWE4 | ⬜ PENDING | |
| Coverage vs target | ADVISORY | ⬜ PENDING | |
