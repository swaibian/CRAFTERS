# Review Issue Template (SWE5)

> Place at position 5, 10, 15… in the TC issue chain.
> Reviews preceding 4 implementation issues, fixes gaps, updates architecture docs.
> Save as: `TC-X-YY_REVIEW_AND_ARCHITECTURE.md`

---

```markdown
# TC-X-YY: Batch [N] Review & Architecture Update

**Component**: [Component Name]
**Epic**: [Epic ID and Name]
**V-Model**: SWE5-X-YY
**Type**: 🔍 REVIEW & ARCHITECTURE
**Priority**: P1-High
**Reviews**: TC-X-[YY-4] through TC-X-[YY-1]
**SW-REQ**: [All SW-REQs covered by reviewed issues]

---

## ⚠️ REVIEW ISSUE — NO NEW FEATURES

This issue REVIEWS the preceding 4 issues, FIXES gaps, and UPDATES architecture docs.
V-Model: SWE5 (Integration Verification) + SWE2 (Architecture).

---

## 📋 Tasks

### 0.0 Read Architecture Docs [MANDATORY]
- [ ] Read `architecture/README.md` + all diagrams + traceability matrix

### 0.1 Read All 4 Predecessor Reports [MANDATORY]
- [ ] Read `TC-X-00_COMPONENT_DEFINITION.md`
- [ ] Read completion reports for TC-X-[YY-4] through TC-X-[YY-1]

### 0.2 Run Test Suite [MANDATORY GATE 🔴]
- [ ] Run all tests. Record baseline. 0 new failures allowed.
- [ ] **Run typecheck** (e.g., `tsc --noEmit`). Record error count.
- [ ] **Run linter** (e.g., `eslint .`). Record error + warning count.

### 1. Code Review
- [ ] Review all changes from TC-X-[YY-4..YY-1]
- [ ] Check: semantic correctness, data flow, error handling, style, dead code
- [ ] Document findings: `| Issue | Finding | Severity | Action |`

### 2. Gap Analysis
- [ ] Acceptance criteria vs delivery, requirements coverage, untested paths
- [ ] Document gaps: `| Gap | Type | Impact | Resolution |`
- [ ] Audit logger adoption for every changed path: event schema, request/user
      context propagation, redaction, and separation from audit/metrics.
- [ ] **Deferral escalation check**: For every gap being deferred, search ALL predecessor completion reports and the coverage map for the same gap. If this gap was already deferred once → auto-escalate to **MEDIUM** and fix in this issue. If deferred twice → escalate to **HIGH** (mandatory fix). A gap may NOT be deferred more than twice across the entire epic.

### 2.5 Build Verification [MANDATORY]
- [ ] Compare typecheck error count to predecessor baseline — any **new** errors introduced by this batch are a MEDIUM finding
- [ ] Compare lint error count to predecessor baseline — any **new** errors introduced by this batch are a MEDIUM finding
- [ ] **Fix tooling configuration issues** in this review issue (e.g., missing globals in the lint config, test files excluded from tsconfig project)
- [ ] Document findings in the findings table

### 3. Fix Findings
- [ ] Fix HIGH/CRITICAL immediately. MEDIUM < 30min effort. LOW → defer.

### 4–8. Architecture Documentation
- [ ] **4**: Update `diagrams/component-overview.md` (new components, changed interfaces)
- [ ] **5**: Update `diagrams/data-model.md` + `api-contracts.md` + `flow-*.md` as needed
- [ ] **6**: Update `traceability/requirements-matrix.md` + `coverage-map.md`
- [ ] **7**: Audit all Key Decisions from the batch's completion reports. Any decision matching these triggers → create an ADR: new API/route pattern, new cross-module coupling pattern, new infrastructure pattern, deviation from established patterns. If no triggers match, document "No ADR-worthy decisions in this batch" in the completion report.
- [ ] **8**: Update `architecture/README.md` (stack, links, change log). **If this is the last review issue for a TC**: add "TC-X COMPLETE" entry to the status block and update the "Last updated by" header with this issue ID and date.

### 9. Integration Tests
- [ ] Write tests for cross-module interactions from the batch
- [ ] Tag distinctly from unit tests (naming or test runner scopes)
- [ ] Include at least one cross-module logging assertion and a no-secret/PII
      assertion; record `N/A` only with a specific evidence-backed rationale.
- [ ] **Runtime wiring verification**: At least one integration test MUST exercise the actual app bootstrap path (or a test harness that mirrors it). Directly constructing a class via `new` does NOT count as integration testing — the test must verify the class is instantiated through the real entry point (e.g., ASGI app bootstrap, FastAPI router include, Django URLConf, React router).
- [ ] **API round-trip test** (if applicable): At least one test must verify the full request path: frontend call → controller endpoint → model/DB → response back to the caller (or MCP client → tool call → module → response).

### 9.5 Runtime Smoke Test [MANDATORY GATE 🔴 — last review issue of each TC]
> If this is the last review issue for this TC, this gate is MANDATORY.
> For mid-TC review issues, this gate is 🟡 CONDITIONAL (run if environment supports it).
- [ ] **Start the application** (or headless equivalent — e.g., `make run-model`, `make run-controller`, `make run-view`)
- [ ] **Trigger the feature** delivered by this TC (e.g., create a work, open a chat, call an MCP tool)
- [ ] **Verify observable output** (row created, endpoint responding, UI element rendered, MCP response received)
- [ ] If the feature cannot be exercised in the running app → this is a **HIGH finding** (wiring gap)

### 10. Test Suite + Coverage [MANDATORY GATE 🔴]
- [ ] Run all tests. Coverage must not regress from Task 0.2 baseline.
- [ ] **Run typecheck** — error count must not exceed Task 0.2 baseline (ideally reduced by fixes in Task 2.5/3).
- [ ] **Run linter** — error count must not exceed Task 0.2 baseline.

### 11. Handover [MANDATORY]
- [ ] Complete completion report: findings, fixes, arch changes, test health
- [ ] Update TC-X-00: status, decisions, arch docs revision

---

## Constraints
- No new features. Bug fixes limited to review findings.
- Deferred items must reference a future issue.
- All diagrams use Mermaid (see ARCHITECTURE_DOC_GUIDE.md).

---

## Acceptance Criteria
- [ ] All HIGH/CRITICAL findings fixed
- [ ] Architecture diagrams reflect current state
- [ ] Traceability matrix updated
- [ ] Integration tests cover cross-module interactions
- [ ] Full suite passing, coverage not regressed
- [ ] Handover written for next batch
- [ ] Logging/observability notes updated where the batch changes a runtime
      boundary

---

## Gate Results

| Gate | Level | Result | Notes |
|------|-------|--------|-------|
| Pre-check (0.2) | SWE4 | ⬜ PENDING | |
| Post-fix (10) | SWE5 | ⬜ PENDING | |
| Coverage | SWE5 | ⬜ PENDING | |
```
