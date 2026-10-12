# Issue Template (SWE3 — Implementation)

> Copy this template when creating a new issue file `TC-X-YY_TITLE.md`.
> Replace all `[placeholders]`. Do NOT omit sections.
>
> **V-Model Level**: SWE3 (Detailed Design + Unit Construction)
> **Verification**: SWE4 (Unit Tests — MANDATORY in every issue)
>
> For review issues (every 5th), use `REVIEW_ISSUE_TEMPLATE.md` instead.

---

```markdown
# TC-X-YY: [Issue Title]

**Component**: [Component Name]
**Epic**: [Epic ID and Name]
**V-Model**: SWE3-X-YY
**Type**: 🔨 IMPLEMENTATION
**Priority**: P0-Critical | P1-High | P2-Medium | P3-Low
**Estimated Effort**: XS | S | M | L | XL
**Dependencies**: [List predecessor issues]
**SW-REQ**: [Link to requirement file]

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

[What this does, why it matters, what breaks if it fails.]

**High Stakes**: [Impact on user/business if this fails]
**Constraints**: [Performance, security, or compatibility constraints]

---

## 🏗️ Architectural Context

[Where this fits in the system. Data flow diagram.]

```
[Input Source] → Your Code → [Output Consumer]
```

See: `project_management/architecture/README.md` for full context.

---

## Traceability

| Level | ID | Artifact |
|-------|-----|---------|
| SYS1 | SYS1-XXX | Epic: EPIC_XXX_NAME.md |
| SWE1 | SWE1-X | TC: TC-X-00_COMPONENT_DEFINITION.md |
| SWE3 | SWE3-X-YY | This issue |
| SWE4 | — | Unit tests in: [test file paths] |

---

## 📋 Task List

### 0.0 Read Architecture Documentation [MANDATORY]
- [ ] **Read: `project_management/architecture/README.md`**
- [ ] **Read: relevant diagrams** in `project_management/architecture/diagrams/`
  for the area this issue changes

> Understand the current system architecture before making changes.
> If architecture docs don't exist yet, note this — the next review issue will create them.

### 0.1 Read Predecessor Context [MANDATORY]
- [ ] **Read: `TC-X-00_COMPONENT_DEFINITION.md`**
- [ ] **Read: `TC-X-{YY-1}_COMPLETION_REPORT.md`** ← predecessor's handoff

> ⚠️ Do NOT skip. The predecessor may have been a different team.
> Their completion report contains decisions, API surfaces, schema
> changes, deviations, and open risks that directly affect this work.

### 0.2 Run Full Test Suite [MANDATORY GATE 🔴]
- [ ] Execute the project's configured test runner (all scopes)
- [ ] **Run typecheck** (e.g., `tsc --noEmit`, `pyright`, `mypy`) [MANDATORY GATE 🔴]
- [ ] **Run linter** (e.g., `eslint .`, `ruff check`, `clippy`) [ADVISORY 🟢 on TC-X-01 / MANDATORY 🔴 from TC-X-02]
- [ ] Record baseline: total tests, passing, failing, skipped, coverage %, typecheck errors, lint errors
- [ ] **Gate**: If new test failures OR new typecheck errors vs. known baseline, STOP and investigate.
  Pre-existing failures in unrelated modules may be documented and accepted.

> The test runner is project-specific. Detect from:
> package.json scripts, pyproject.toml, Makefile, *.csproj, go.mod, Cargo.toml, etc.
> See V_MODEL_FRAMEWORK.md §4 for typecheck and lint detection rules.

### 1. Investigate Requirements
- [ ] Read: [specific requirement files with paths]
- [ ] Read: [specific architecture/code files with paths]

### 1.5 Logging & Observability Integration [MANDATORY CROSS-CUTTING]
- [ ] Read: `docs/mvc_architecture.md` and the project logger setup in the
      layer(s) this issue touches (`src/model`, `src/controller`, `src/mcp`,
      `src/view`).
- [ ] Identify every runtime boundary changed by this issue and instrument it
      through the project logger, or record a specific `N/A — no runtime event`
      rationale in the completion report.
- [ ] Propagate/retain request/user/session context; use only redacted,
      allow-listed fields. Never log tokens, secrets, raw bodies, prompts,
      document content, image data, transcripts, or HTML.
- [ ] Keep operational logs separate from security-audit records and metrics.

### 2. Write/Update Requirements
- [ ] [Specific requirement updates needed]

### 3. Investigate Architecture
- [ ] Review: [specific files with full paths]

### 4. Implement Code
- [ ] [Specific, actionable implementation tasks — not vague]

### 5. Create Unit Tests (SWE4) [MANDATORY]
- [ ] [Specific tests to write]
- [ ] Each new module/function MUST have corresponding unit tests
- [ ] Test both happy path and error cases
- [ ] Test logger event schema, context propagation, and redaction for every
      changed logging boundary (or the documented N/A rationale).

### 6. Run Full Test Suite + Coverage [MANDATORY GATE 🔴]
- [ ] Execute test runner (all scopes)
- [ ] **Run typecheck** — 0 new errors vs. Task 0.2 baseline [MANDATORY GATE 🔴]
- [ ] **Run linter** — 0 new errors vs. Task 0.2 baseline [see gate level from 0.2]
- [ ] Record: total tests, passing, failing, skipped, coverage %, typecheck errors, lint errors
- [ ] Compare to Task 0.2 baseline — coverage must not decrease, no new typecheck/lint errors
- [ ] **Gate**: 0 new failures allowed. Coverage must not regress. Typecheck must not regress.

### 7. Create Documentation
- [ ] [Specific docs to write/update]
- [ ] Update inline code documentation for new/changed APIs
- [ ] If schema changed: note for next review issue to update data-model diagram

### 8. Write Completion Report & Handoff [MANDATORY]
- [ ] Complete `TC-X-YY_COMPLETION_REPORT.md`
- [ ] **Write handoff section for TC-X-{YY+1} team** — MUST include:
  - What was built: files created/modified, APIs exposed, schemas changed
  - Key decisions made and why (especially deviations from this plan)
  - Known limitations or edge cases
  - Open risks or questions for the next team
  - Code examples showing how to use what was built
  - Gate results table
- [ ] Update `TC-X-00_COMPONENT_DEFINITION.md` with status + new decisions

---

## ⚠️ Constraints

- [Specific constraints for this issue]

---

## 📁 Files to Modify

| Action | File Path | Description |
|--------|-----------|-------------|
| Create | `path/to/new/file.ext` | Description |
| Update | `path/to/existing.ext` | What to change |
| Read   | `path/to/reference.md` | Reference material |

---

## ✅ Acceptance Criteria

- [ ] [Specific, measurable criterion]
- [ ] All unit tests passing (SWE4)
- [ ] Coverage not regressed from Task 0.2 baseline
- [ ] Completion report written with handoff for next team
- [ ] TC-X-00 updated with status and decisions
- [ ] Logger evidence included: event names/fields, request/user context path,
      redaction tests, and audit/metrics separation

---

## 📖 Reference Documents

- V-Model Framework: `project_management/swaibian_V-Model_Agents/_templates/V_MODEL_FRAMEWORK.md`
- Architecture: `project_management/architecture/README.md`
- MVC architecture: `docs/mvc_architecture.md`
- Repo rules (DB protection, commands, stack): `AGENTS.md`
- Epic: `project_management/epics/EPIC_XXX_NAME.md`
- Component: `project_management/epics/EPIC_XXX_NAME/TC_X_<SUMMARIZED_CONTENT>/TC-X-00_COMPONENT_DEFINITION.md`
- Predecessor Report: `project_management/epics/EPIC_XXX_NAME/TC_X_<SUMMARIZED_CONTENT>/TC-X-{YY-1}_COMPLETION_REPORT.md`
- SW Requirements: `project_management/requirements/SW-REQXXX.md`

---

## 🔗 Related Issues

- Depends On: [predecessor issues]
- Blocks: [successor issues]
- Related: [related but not dependent]

---

## Gate Results (filled during execution)

| Gate | Level | Result | Notes |
|------|-------|--------|-------|
| Pre-check test suite (Task 0.2) | SWE4 | ⬜ PENDING | |
| Post-implementation suite (Task 6) | SWE4 | ⬜ PENDING | |
| Coverage vs baseline | SWE4 | ⬜ PENDING | |
| Coverage vs target | ADVISORY | ⬜ PENDING | |
```
