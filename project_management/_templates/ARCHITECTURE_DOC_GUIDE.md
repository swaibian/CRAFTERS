# Architecture Documentation Guide

> Instructions for creating and maintaining project architecture docs.
> Read by review issues (SWE5) and architecture scaffold agents.
> Technology-agnostic.

---

## 1. Folder Structure

```
project_management/architecture/
  README.md                    ← Living architecture overview (entry point)
  diagrams/
    component-overview.md      ← Mermaid: system components
    data-model.md              ← Mermaid: ERD / schema
    api-contracts.md           ← Mermaid: API sequences
    flow-*.md                  ← Mermaid: functional flows
  traceability/
    requirements-matrix.md     ← SYS1→SWE1→SWE3→SWE4 mapping
    coverage-map.md            ← Requirements → test coverage
  decisions/
    ADR-NNN-short-title.md     ← Architecture Decision Records
```

---

## 2. Mermaid Diagrams

All diagrams use Mermaid (renders in GitHub + VS Code). Each file needs:
- `Last updated by: [Issue ID]` header
- One primary Mermaid diagram
- A companion table describing elements

### Diagram Types

| File | Mermaid Type | Update When |
|------|-------------|-------------|
| `component-overview.md` | `graph TB` | New component or interface change |
| `data-model.md` | `erDiagram` | Schema migration |
| `api-contracts.md` | `sequenceDiagram` | New endpoint or flow change |
| `flow-*.md` | `flowchart TD` | Logic change in key workflow |

### Quality Rules
- Every code component must appear in component diagram
- Every DB table must appear in data model
- API sequences must match actual endpoint signatures
- No orphaned elements (in diagram but not in code, or vice versa)

---

## 3. ADR Format

Create `decisions/ADR-NNN-short-title.md` when:
- Technology/library choice made
- Significant design pattern chosen
- Breaking architecture change introduced

```markdown
# ADR-NNN: [Title]
**Status**: Proposed | Accepted | Deprecated | Superseded by ADR-XXX
**Date**: YYYY-MM-DD  |  **Issue**: [Issue ID]  |  **V-Model**: SWE2

## Context
[Problem requiring a decision]

## Decision
[What was decided and why]

## Alternatives
| Alt | Pros | Cons | Why Rejected |
|-----|------|------|-------------|

## Consequences
- Positive: [benefits]
- Negative: [trade-offs]
- Risks: [risks + mitigation]
```

Sequential numbering. Never reuse numbers.

**Review issue mandate**: Every review issue (SWE5) must audit its batch's completion report Key Decisions tables. Each decision must be evaluated against the triggers above. Decisions not elevated to ADR must have an explicit note in the review completion report ("No ADR created for [decision] because [reason]").

---

## 4. Traceability Matrix

**File**: `traceability/requirements-matrix.md`

```markdown
| SYS1 | SWE1 | SW-REQ | SWE3 (Issue) | SWE4 (Unit) | SWE5 (Integration) | Status |
|------|------|--------|-------------|-------------|-------------------|--------|
```

**Update rules**:
- Implementation issues: add row for new code + unit test
- Review issues: audit matrix completeness
- TC boundary: verify all SWE1 requirements have SWE3 mapping

**Coverage map**: `traceability/coverage-map.md` — summary of coverage per SW-REQ.

---

## 5. Architecture README

**File**: `architecture/README.md` — entry point read by every agent at Task 0.0.

Required sections:
1. Purpose (2-3 sentences)
2. Technology Stack (table)
3. System Architecture → link to component-overview.md
4. Data Model → link to data-model.md
5. API Contracts → link to api-contracts.md
6. Key Flows → links to flow-*.md
7. Architecture Decisions → ADR table
8. Traceability → links to matrix + coverage map
9. Change Log (date, issue, change)

**Update rules**: swaibian-architect creates scaffold; review issues (SWE5) update all sections.

---

## 6. Update Triggers

| Event | Files to Update |
|-------|----------------|
| New API endpoint | api-contracts.md, requirements-matrix.md |
| DB migration | data-model.md, requirements-matrix.md |
| New component | component-overview.md, README.md |
| Architecture decision | New ADR, README.md §7 |
| Review issue (SWE5) | ALL — full audit |
