# Epic Template

> Copy this template when creating a new Epic file `project_management/epics/EPIC_XXX_NAME.md`.
> After creating, update `project_management/epics/EPIC_OVERVIEW.md` with the new entry.
>
> **V-Model Level**: SYS1 (System Requirements) + SYS2 (System Architecture)

---

```markdown
# Epic XXX: [Epic Name]

**ID**: E-XXX
**V-Model**: SYS1-XXX
**Status**: 🔲 Planning | 🔄 In Progress | ✅ Complete
**Priority**: P0-Critical | P1-High | P2-Medium | P3-Low
**Created**: YYYY-MM-DD
**Last Updated**: YYYY-MM-DD

---

## Vision

[2-3 sentences: what this epic delivers and the user/business problem it solves.]

## Goals

1. [Concrete, measurable goal]
2. [Concrete, measurable goal]
3. [Concrete, measurable goal]

## Scope

### In Scope
- [What's included]

### Out of Scope
- [What's explicitly excluded]

## Requirements (SYS1)

| Requirement | Title | V-Model | Link |
|:------------|:------|:--------|:-----|
| REQ-XXX | [Title] | SYS1 | [path to requirement file] |
| SW-REQ-XXX | [Title] | SWE1 | [path to requirement file] |

## System Architecture (SYS2)

> High-level architecture for this epic. Detailed diagrams live in
> `project_management/architecture/diagrams/`.

### Key Architectural Decisions
| Decision | Choice | Rationale | ADR |
|----------|--------|-----------|-----|
| [e.g. Database] | [e.g. SQLite] | [Why] | [ADR-NNN or "none yet"] |

### Component Interaction
[Describe or link to Mermaid diagram showing how this epic's TCs interact]

## Technical Components

| TC | Name | V-Model | Issues | Review Issues | Status |
|:---|:-----|:--------|:-------|:--------------|:-------|
| TC-A | [Name] | SWE1-A | [count] | [at positions 5,10...] | 🔲 |
| TC-B | [Name] | SWE1-B | [count] | [at positions 5,10...] | 🔲 |

## Test Plan

| V-Level | Test Type | Scope | Gate | Notes |
|---------|-----------|-------|------|-------|
| SWE4 | Unit tests | Every issue | 🔴 MANDATORY | Project test runner |
| SWE5 | Integration tests | Every 5th issue | 🔴 MANDATORY | Cross-module |
| SWE6 | TC acceptance | TC completion | 🟡 CONDITIONAL | If acceptance suite exists |
| SYS3 | E2E / system | Epic completion | 🟡 CONDITIONAL | If headless env available |

## Dependencies

- [External dependencies, other epics, API contracts, etc.]

## Risks

| Risk | Impact | Mitigation |
|:-----|:-------|:-----------|
| [Risk] | [Impact] | [Mitigation] |
```
