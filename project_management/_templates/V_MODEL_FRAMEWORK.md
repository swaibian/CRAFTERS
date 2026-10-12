# V-Model Development Framework

> **Purpose**: Master reference for the V-Model-aligned development process used
> across all software projects. Read by all planning and execution agents.
>
> **Inspired by**: Automotive ASPICE (SYS.1–SYS.4, SWE.1–SWE.6) adapted for
> AI-pipeline-driven agile development.

---

## 1. V-Model Level Map

```
              REQUIREMENTS SIDE                           VERIFICATION SIDE
        ┌──────────────────────────┐               ┌──────────────────────────┐
  SYS1  │  System Requirements      │ ←──────────→ │  System Qualification     │  SYS4
        │  (Epic)                   │               │  (Release gate)           │
        └─────────┬────────────────┘               └──────────────────────────┘
                  │ decomposes into                              ↑ qualifies
  SYS2  ┌────────┴─────────────────┐               ┌──────────────────────────┐
        │  System Architecture      │ ←──────────→ │  System Integration Test  │  SYS3
        │  (Epic-level arch docs)   │               │  (E2E at epic boundary)   │
        └─────────┬────────────────┘               └──────────────────────────┘
                  │ allocated to                                 ↑ integrates
  SWE1  ┌────────┴─────────────────┐               ┌──────────────────────────┐
        │  SW Requirements (TC)     │ ←──────────→ │  SW Qualification Test    │  SWE6
        │  (Component Definition)   │               │  (TC acceptance tests)    │
        └─────────┬────────────────┘               └──────────────────────────┘
                  │ designed in                                  ↑ integration tested
  SWE2  ┌────────┴─────────────────┐               ┌──────────────────────────┐
        │  SW Architecture          │ ←──────────→ │  SW Integration Test      │  SWE5
        │  (Mermaid docs, ADRs)     │               │  (Every 5th review issue) │
        └─────────┬────────────────┘               └──────────────────────────┘
                  │ detailed in                                  ↑ unit tested
  SWE3  ┌────────┴─────────────────┐               ┌──────────────────────────┐
        │  Detailed Design + Code   │ ←──────────→ │  Unit Verification        │  SWE4
        │  (Issue implementation)   │               │  (Every issue)            │
        └──────────────────────────┘               └──────────────────────────┘
```

---

## 2. Artifact-to-Level Mapping

| V-Level | Artifact | Current Equivalent | ID Pattern | Created By |
|---------|----------|-------------------|------------|------------|
| **SYS1** | Epic Definition | `EPIC_XXX_NAME.md` | `SYS1-XXX` | swaibian-architect |
| **SYS2** | System Architecture Docs | `architecture/README.md` (per epic) | — | swaibian-architect scaffolds, review issues maintain |
| **SWE1** | Component Definition (TC) | `TC-X-00_COMPONENT_DEFINITION.md` | `SWE1-X` | swaibian-architect |
| **SWE2** | SW Architecture Docs | `architecture/diagrams/*.md` | — | Review issues (every 5th) |
| **SWE3** | Issue (implementation) | `TC-X-YY_TITLE.md` | `SWE3-X-YY` | swaibian-architect |
| **SWE4** | Unit Tests | Project test runner (unit scope) | — | swaibian-impl (every issue) |
| **SWE5** | Integration Tests | Project test runner (integration scope) | — | Review issues (every 5th) |
| **SWE6** | TC Acceptance Tests | TC completion test scope | — | TC driver at TC boundary |
| **SYS3** | E2E / System Integration Tests | Headless browser or API-level | — | Epic boundary + last review issue of each TC (smoke test) |
| **SYS4** | Full Qualification | All of the above + manual checklist | — | Release gate |

---

## 3. Naming & Tagging Convention

Every artifact carries a V-Model tag in its header for traceability.

### Epic (SYS1)
```
**V-Model**: SYS1-001
**ID**: E-001
```

### Component Definition (SWE1)
```
**V-Model**: SWE1-A (derived from SYS1-001)
```

### Issue — Implementation (SWE3)
```
**V-Model**: SWE3-A-01
**Verifies**: SWE4 (unit tests in this issue)
```

### Issue — Review (SWE5)
```
**V-Model**: SWE5-A-05
**Reviews**: SWE3-A-01 through SWE3-A-04
**Produces**: SWE2 architecture updates, SWE5 integration tests
```

### Traceability Chain
```
SYS1-001 (Epic)
  └→ SWE1-A (TC-A Component Definition)
       └→ SWE3-A-01 (Issue 01) → SWE4 (unit tests)
       └→ SWE3-A-02 (Issue 02) → SWE4 (unit tests)
       └→ SWE3-A-03 (Issue 03) → SWE4 (unit tests)
       └→ SWE3-A-04 (Issue 04) → SWE4 (unit tests)
       └→ SWE5-A-05 (Review Issue) → SWE5 (integration tests) + SWE2 (arch docs)
```

---

## 4. Gate Classifications

| Gate Type | Symbol | Meaning | Pipeline Behavior |
|-----------|--------|---------|-------------------|
| **MANDATORY** | 🔴 | Must pass. Pipeline blocks. | Agent stops on failure, attempts fix, escalates if unresolvable |
| **CONDITIONAL** | 🟡 | Run if environment supports it. Skip with documented reason if not. | Agent checks capability first, skips gracefully with `GATE SKIPPED` note |
| **ADVISORY** | 🟢 | Best effort. Failure is logged, not blocking. | Agent reports finding in completion report, continues |

### Gate Application by Level

| V-Level | Test Scope | Gate | Agent Behavior |
|---------|-----------|------|----------------|
| **SWE4** | Unit tests | 🔴 MANDATORY | Run project test runner, unit scope. 0 failures allowed. |
| **SWE4-BUILD** | Typecheck (`tsc --noEmit` or equiv.) | 🔴 MANDATORY | Run static type checker. 0 new errors vs baseline. |
| **SWE4-LINT** | Lint (`eslint .` or equiv.) | 🟢 ADVISORY on TC-X-01 → 🔴 MANDATORY from TC-X-02 | First issue may bootstrap config; from issue 02 onward, 0 new errors allowed. |
| **SWE5** | Integration tests | 🔴 MANDATORY | Run project test runner, integration scope. 0 failures allowed. |
| **SWE6** | TC acceptance | 🟡 CONDITIONAL | Run if TC acceptance suite exists. Skip with note if not. |
| **SYS3** | E2E / system tests | 🟡 CONDITIONAL → 🔴 MANDATORY for last review issue of each TC | Run if headless test environment available. Last review issue of each TC MUST run a runtime smoke test (start app → trigger feature → verify output). Skip only if no display/browser AND document as HIGH gap. |
| **SYS4** | Full qualification | 🟢 ADVISORY | Run what's possible in CI. Log what needs manual verification. |

> **SWE4-BUILD rationale**: TypeScript strict-null errors, Python type errors, etc. accumulate silently
> if only unit tests are gated. Typecheck catches structural regressions that tests may miss.
>
> **SWE4-LINT rationale**: Lint starts ADVISORY on TC-X-01 because the config may not be mature.
> From TC-X-02 onward it becomes MANDATORY — the first review issue (TC-X-05) validates the config.

### Environment Detection

Before running any gate, the agent detects the project's test infrastructure:

```
Test runner detection:
1. Check package.json → "scripts.test" / "test:unit" / "test:integration"
2. Check pyproject.toml → [tool.pytest] sections
3. Check Makefile / Taskfile → test targets
4. Check *.csproj → test project references  
5. Check go.mod → go test availability
6. Check Cargo.toml → cargo test

Typecheck detection (SWE4-BUILD):
7. Check tsconfig.json → run `npx tsc --noEmit` (or package.json scripts.typecheck)
8. Check pyproject.toml → run `pyright` / `mypy`
9. Check go.mod → `go vet ./...`
10. Check Cargo.toml → `cargo check`

Lint detection (SWE4-LINT):
11. Check eslint.config.js / .eslintrc.* → run `npx eslint .` (or package.json scripts.lint)
12. Check pyproject.toml → run `ruff check .` / `flake8`
13. Check .golangci.yml → run `golangci-lint run`
14. Check Cargo.toml → `cargo clippy`

For CONDITIONAL gates, verify environment capability:
- Browser tests: check for headless browser binary
- GUI tests: check for display server ($DISPLAY or equivalent)
- Platform-specific: check OS matches requirement
- External service: check if dependent service is reachable

If a MANDATORY gate cannot run (no test runner found): STOP and report as blocker.
If a CONDITIONAL gate cannot run: SKIP with documented reason and continue.
```

---

## 5. The 5-Issue Batch Cycle

Issues are organized in batches of 5. Every 5th issue is a **Review + Architecture Issue** (SWE5).

### Pattern

```
Batch 1:
  TC-X-01  [SWE3]  Implementation + SWE4 unit tests
  TC-X-02  [SWE3]  Implementation + SWE4 unit tests
  TC-X-03  [SWE3]  Implementation + SWE4 unit tests
  TC-X-04  [SWE3]  Implementation + SWE4 unit tests
  TC-X-05  [SWE5]  REVIEW ISSUE — reviews 01–04, updates architecture, integration tests

Batch 2:
  TC-X-06  [SWE3]  Implementation + SWE4 unit tests
  TC-X-07  [SWE3]  Implementation + SWE4 unit tests
  TC-X-08  [SWE3]  Implementation + SWE4 unit tests
  TC-X-09  [SWE3]  Implementation + SWE4 unit tests
  TC-X-10  [SWE5]  REVIEW ISSUE — reviews 06–09, updates architecture, integration tests
```

### Edge Cases

| Situation | Rule |
|-----------|------|
| TC has &lt; 5 issues | Last issue inherits review responsibilities (use REVIEW_ISSUE_TEMPLATE for last issue) |
| TC has exactly 5 issues | Issue 05 is the review issue |
| TC has 6–9 issues | Issue 05 is review; last issue also inherits review of the remaining issues |
| TC has 10+ issues | Issue 05, 10, 15… are review issues |
| TC has only 1–2 issues | No separate review issue; review is handled by the TC driver + TC boundary review |
| Epic declares `**Review Mode**: no-reviews` (architect no-reviews variant) | No SWE5 review issues and no reviewer subagent is spawned: `swaibian-impl` self-verifies every issue (STEP E-NR); each TC's last issue is the closer and inherits gap analysis, integration tests, arch docs, SYS3 smoke |

### What Review Issues Produce

1. **Gap analysis** of the preceding 4 issues (bugs, inconsistencies, missed requirements)
2. **Bug fixes** for anything found
3. **Architecture documentation updates** (Mermaid diagrams, ADRs)
4. **Requirements traceability matrix update**
5. **Integration tests** (cross-module interactions from the preceding 4 issues)
6. **Handover document** bridging to the next batch

---

## 6. Task Ordering

### Standard Implementation Issue (SWE3)

```
Task 0.0 — Read SW Architecture docs [MANDATORY]
           Read: project_management/architecture/README.md
           Read: relevant Mermaid diagrams for the area being changed

Task 0.1 — Read Handover Context [MANDATORY]
           First issue: read TC-X-00_COMPONENT_DEFINITION.md only
           Subsequent: read TC-X-00 + TC-X-{YY-1}_COMPLETION_REPORT.md

Task 0.2 — Run Full Test Suite [MANDATORY GATE]
           Execute the project's configured test runner (all scopes).
           Gate: 0 failures. If pre-existing failures exist, document them
           and proceed only if they are in unrelated modules.

Task 1..N — Implementation tasks
           (Specific to the issue — code, tests, docs)
           Each implementation task MUST include unit tests (SWE4).

Task N+1 — Run Full Test Suite + Coverage [MANDATORY GATE]
           Execute test runner. Report:
           - Total tests, passing, failing, skipped
           - Coverage percentage vs project target
           If new failures: fix before proceeding.

Task N+2 — Create/Update Handover Document [MANDATORY]
           Complete TC-X-YY_COMPLETION_REPORT.md
           Write handoff section specific to what was built.
           Update TC-X-00_COMPONENT_DEFINITION.md with status + decisions.
```

### Review Issue (SWE5) — Every 5th

See `REVIEW_ISSUE_TEMPLATE.md` for full task structure.

```
Task 0.0 — Read SW Architecture docs
Task 0.1 — Read ALL 4 preceding completion reports
Task 0.2 — Run full test suite [MANDATORY GATE]

─── REVIEW PHASE ───
Task 1   — Code review of issues N+1 through N+4
Task 2   — Gap analysis (requirements coverage, untested paths)
Task 3   — Bug/flaw fixes found in review

─── DOCUMENTATION PHASE ───
Task 4   — Update/create Mermaid component diagrams
Task 5   — Update/create Mermaid sequence/flow diagrams
Task 6   — Update requirements traceability matrix
Task 7   — Update/create Architecture Decision Records (if new decisions)
Task 8   — Update architecture README

─── VERIFICATION PHASE ───
Task 9   — Create/update integration tests (cross-module)
Task 10  — Run full test suite + coverage [MANDATORY GATE]

─── HANDOVER ───
Task 11  — Create handover document for next batch
```

---

## 7. Traceability Requirements

### Every Issue Must Track

```markdown
## Traceability
| Level | ID | Artifact |
|-------|-----|---------|
| SYS1 | SYS1-XXX | Epic: EPIC_XXX_NAME.md |
| SWE1 | SWE1-X | TC: TC-X-00_COMPONENT_DEFINITION.md |
| SWE3 | SWE3-X-YY | This issue |
| SWE4 | — | Unit tests in: [test file paths] |
```

### Requirements Traceability Matrix (maintained by review issues)

```markdown
| SYS1 (Epic) | SWE1 (TC) | SW-REQ | SWE3 (Issue) | SWE4 (Unit Tests) | SWE5 (Integration Tests) | Status |
|---|---|---|---|---|---|---|
| SYS1-001 | SWE1-A | SW-REQ001 | SWE3-A-01 | test/unit/component.test.ts | test/integration/api.test.ts | ✅ |
```

---

## 8. Architecture Documentation Standards

See `ARCHITECTURE_DOC_GUIDE.md` for detailed instructions on:
- Mermaid diagram conventions
- Architecture Decision Records (ADR) format
- Living README maintenance
- Traceability matrix format

### Per-Project Folder Structure (created by swaibian-architect)

```
project_management/
  architecture/
    README.md                          ← Living architecture overview
    diagrams/
      component-overview.md            ← Mermaid: system component diagram
      data-model.md                    ← Mermaid: ERD / schema
      api-contracts.md                 ← Mermaid: API sequence diagrams
      flow-*.md                        ← Mermaid: functional flowcharts
    traceability/
      requirements-matrix.md           ← SYS1 → SWE1 → SWE3 → SWE4 mapping
      coverage-map.md                  ← Which tests cover which requirements
    decisions/
      ADR-001-*.md                     ← Architecture Decision Records
```

---

## 9. TC Boundary Rules

When a TC completes (all issues done):

1. **TC driver** runs TC acceptance tests (SWE6 — CONDITIONAL)
2. **TC driver** verifies all issues have completion reports
3. **TC driver** verifies architecture docs are current (last review issue updated them)
4. **TC driver** updates `TC-X-00` Status field to ✅ Complete
5. **TC driver** updates the epic header file: sets this TC's row to ✅, updates `Last Updated` date
6. If TC is the last in an epic → trigger Epic Boundary Rules below

### Epic Boundary Rules

When an epic completes (all TCs done):

1. Run SYS3 system integration tests (CONDITIONAL — headless E2E if available)
2. Update epic header: Status → ✅ Complete, confirm all TC rows are ✅, update `Last Updated`
3. Update `EPIC_OVERVIEW.md` with completion status
4. Update `architecture/README.md`: "Last updated by" header with final issue ID and date, epic-level changes
5. Run full test suite one final time (MANDATORY)

---

## 10. Glossary

| Term | Meaning |
|------|---------|
| **Gate** | A test/check that must pass before proceeding. See §4. |
| **Batch** | A group of 4 implementation issues + 1 review issue. See §5. |
| **Review Issue** | Every 5th issue — reviews preceding 4, updates docs. See §5. |
| **ADR** | Architecture Decision Record — documents a significant design choice. |
| **MANDATORY** | Must pass. Pipeline blocks on failure. |
| **CONDITIONAL** | Run if environment supports it. Skip with documented reason. |
| **ADVISORY** | Best effort. Log result, continue regardless. |
| **SWE4-BUILD** | Typecheck gate — static type verification (e.g. `tsc --noEmit`). MANDATORY. See §4. |
| **SWE4-LINT** | Lint gate — code style/quality linter (e.g. `eslint .`). ADVISORY on TC-X-01, MANDATORY from TC-X-02. See §4. |

---

*This framework applies to all software projects regardless of technology stack.
The test runner, language, and tooling are project-specific — the process is universal.*
