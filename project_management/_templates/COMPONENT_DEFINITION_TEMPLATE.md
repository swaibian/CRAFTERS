# Component Definition Template

> Copy this template when creating `TC-X-00_COMPONENT_DEFINITION.md`.
> This is the **shared context document** for all issues in a Technical Component.
> Every issue reads it before starting. Every issue updates it after completing.
>
> **V-Model Level**: SWE1 (SW Requirements)

---

```markdown
# TC-X-00: [Component Name] — Component Definition

> **Epic**: [Epic ID and link]
> **V-Model**: SWE1-X (derived from SYS1-XXX)
> **Requirements**: [SW-REQ link]
> **Review Mode**: impl-review-loop | no-reviews (no-reviews → impl
> self-verifies per STEP E-NR; no reviewer is spawned)
> **Status**: 🔲 Not Started | 🔄 In Progress | ✅ Complete
> **Last Updated**: YYYY-MM-DD

---

## Component Goal

[2-3 sentences: what this component delivers and why it matters.]

## Responsibilities

1. **[Responsibility 1]** — [brief description]
2. **[Responsibility 2]** — [brief description]
3. **[Responsibility 3]** — [brief description]

## Logging & Observability Allocation (mandatory cross-cutting)

Every component uses the project logger at its runtime boundaries; it must not
create a private logging setup. Read `docs/mvc_architecture.md` and allocate at
least one issue to instrument the component's runtime boundaries, or document
and test `N/A — no runtime event`. Each issue must preserve request/user/session
context, never log secrets or PII, keep security audit and metrics separate, and
hand off event/test evidence. The SWE5 review verifies the real bootstrap wiring
and no unapproved direct `console.*` / `print()` path.

## Integration Points

| Direction | Component | Interface |
|:----------|:----------|:----------|
| **Uses** | [Component name] | [What interface/API] |
| **Provides to** | [Component name] | [What this component exposes] |

## Runtime Instantiation Map

> **MANDATORY** — every component must document WHERE it is created and HOW it is
> exposed to the rest of the application. This prevents modules from being built
> in isolation without ever being wired into the running app.

| Component Class | Instantiated In | Lifecycle Owner | Route / Tool / Export Path |
|:----------------|:----------------|:----------------|:---------------------------|
| `[ClassName]` | `[file that calls new / creates instance]` | `[who starts/stops it]` | `[FastAPI route, MCP tool, React route, export, or direct call]` |

> **Rules**:
> - If a class exists but has no row here → it is dead code. Either add a row or remove the class.
> - At least one implementation issue in each TC MUST own "wire into [file]" as an explicit responsibility.
> - The review issue (SWE5) MUST verify every row: class exists, instantiation file imports it, route/tool/export path is registered.

## Architecture References

| Artifact | Path | Relevance |
|----------|------|-----------|
| Component Overview | `project_management/architecture/diagrams/component-overview.md` | [Where this TC fits] |
| Data Model | `project_management/architecture/diagrams/data-model.md` | [Tables this TC owns] |
| API Contracts | `project_management/architecture/diagrams/api-contracts.md` | [Endpoints this TC defines] |
| Logging & Observability | `docs/mvc_architecture.md` | [Where boundary logging is configured; redaction obligations] |

## Key Files

| Action | File | Purpose |
|:-------|:-----|:--------|
| Create/Update | `path/to/file.ext` | [Purpose] |

## Issues

| Issue | Title | Type | V-Model | Priority | Effort | Status |
|:------|:------|:-----|:--------|:---------|:-------|:-------|
| [TC-X-01](TC-X-01_TITLE.md) | [Title] | 🔨 Impl | SWE3-X-01 | [Priority] | [Effort] | 🔲 |
| [TC-X-02](TC-X-02_TITLE.md) | [Title] | 🔨 Impl | SWE3-X-02 | [Priority] | [Effort] | 🔲 |
| [TC-X-03](TC-X-03_TITLE.md) | [Title] | 🔨 Impl | SWE3-X-03 | [Priority] | [Effort] | 🔲 |
| [TC-X-04](TC-X-04_TITLE.md) | [Title] | 🔨 Impl | SWE3-X-04 | [Priority] | [Effort] | 🔲 |
| [TC-X-05](TC-X-05_REVIEW.md) | Batch 1 Review & Architecture | 🔍 Review | SWE5-X-05 | P1-High | M | 🔲 |

## Acceptance Test Plan (SWE6)

> Filled in by swaibian-architect during planning, verified by the TC driver at TC completion.

| # | Acceptance Criterion | Test Type | Gate |
|---|---------------------|-----------|------|
| 1 | [Criterion from SW-REQ] | Unit / Integration | 🔴 / 🟡 |
| 2 | [Criterion from SW-REQ] | Unit / Integration | 🔴 / 🟡 |

## Decisions Log

| Date | Decision | Rationale | ADR |
|:-----|:---------|:----------|:----|
| YYYY-MM-DD | [Decision] | [Why] | [ADR-NNN or —] |

## Architecture Documentation Revisions

| Date | Issue | Changes Made |
|------|-------|-------------|
| YYYY-MM-DD | TC-X-05 | [Initial architecture documentation] |

---

*Shared context document — read before starting any TC-X issue, update after completing each one.*
```

---

## Usage Notes

### When to update this file
- **After completing each issue**: update the Issues table status, add new decisions
- **After review issues (SWE5)**: add Architecture Documentation Revisions entry
- **When the last issue completes**: set the top-level `Status` field to ✅ Complete (not just individual issue rows)
- **When a decision changes**: record the change and rationale, create ADR
- **When review findings are added**: add a Review Findings section

### What NOT to put here
- Implementation details that belong in the completion report
- Test results (those go in the completion report)
- Detailed code documentation (that goes in code docs or architecture folder)
