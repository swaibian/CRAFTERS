# Discovery Brief Template

> **Created by**: swaibian-discovery agent
> **Consumed by**: swaibian-architect agent
>
> This is the handoff artifact from the discovery phase. The architecture agent
> reads this before creating any epic, TC, or issue files.
> Save as: `project_management/epics/EPIC_XXX_NAME/DISCOVERY_BRIEF.md`

---

```markdown
# Discovery Brief: [Feature / Epic Name]

**Date**: YYYY-MM-DD
**Participants**: [Who was involved in the discovery session]
**Status**: ✅ Ready for Architecture | 🔄 Needs More Discovery

---

## 1. Problem Statement

[What problem are we solving? Who has this problem? What happens if we don't solve it?]

## 2. Agreed Scope

### In Scope
- [Concrete deliverable 1]
- [Concrete deliverable 2]

### Out of Scope
- [Explicitly excluded item 1]
- [Explicitly excluded item 2]

### Open Questions (unresolved)
- [Question that couldn't be answered during discovery]

## 3. User Stories / Use Cases

| # | As a... | I want to... | So that... | Priority |
|---|---------|-------------|------------|----------|
| 1 | [role] | [action] | [benefit] | P0/P1/P2 |
| 2 | [role] | [action] | [benefit] | P0/P1/P2 |

## 4. Technology Decisions

| Decision | Choice | Rationale | Alternatives Considered |
|----------|--------|-----------|------------------------|
| [e.g. State management] | [e.g. Zustand] | [Why] | [What else was discussed] |
| [e.g. Protocol] | [e.g. WebSocket] | [Why] | [REST polling, SSE] |

## 5. UI / UX Requirements

- **Layout**: [Description or reference to mockup]
- **Key interactions**: [What the user does step by step]
- **Accessibility**: [Any specific requirements]
- **Responsive**: [Desktop-only / responsive / etc.]

## 6. Constraints & Risks

| Type | Description | Impact | Mitigation |
|------|-------------|--------|------------|
| Technical | [e.g. No backfill protocol exists] | [Blocks offline sync] | [Raise RFC] |
| Security | [e.g. Token exposure risk] | [Auth bypass] | [Use httpOnly cookies] |
| Performance | [e.g. Large message history] | [Slow load] | [Pagination] |

## 7. Existing Requirements Found

| Requirement | Title | Relevance |
|-------------|-------|-----------|
| REQ-XXX | [Title] | [How it relates] |
| SW-REQ-XXX | [Title] | [How it relates] |

*If no existing requirements match, state: "No existing requirements found — new REQ/SW-REQ needed."*

## 8. Brainstorming Outcomes

### Accepted Ideas
- [Idea 1]: [Brief description, why accepted]
- [Idea 2]: [Brief description, why accepted]

### Rejected Ideas
- [Idea 1]: [Brief description, why rejected]
- [Idea 2]: [Brief description, why rejected]

### Deferred Ideas (future consideration)
- [Idea 1]: [Brief description, why deferred]

## 9. V-Model Scope Classification

> The architecture agent uses this to set the correct V-Model level tags
> and determine what test levels are needed.

| Aspect | Classification | Notes |
|--------|---------------|-------|
| System Impact | 🔴 Core / 🟡 Module / 🟢 Leaf | [Does this change system architecture or is it isolated?] |
| Integration Scope | Multi-component / Single-component | [How many TCs will need integration?] |
| Test Level Needed | SWE4 only / SWE4+SWE5 / Full V (SWE4-SYS4) | [Unit tests enough, or integration/E2E needed?] |
| Architecture Docs Exist? | Yes / Partial / No | [Will the first batch need to create arch docs from scratch?] |
| Estimated Batch Count | [N] batches of 5 | [Total issues / 5, rounded up] |

> **Guidelines**:
> - **Core**: Changes to shared infrastructure, data models, APIs used by multiple components
> - **Module**: Changes scoped to one component but with integration points
> - **Leaf**: Fully isolated changes (UI tweaks, config, single utility)
>
> - If **Architecture Docs Exist? = No**, the first review issue (Issue 5) should prioritize
>   creating the architecture folder structure and baseline diagrams.

## 10. Suggested Component Breakdown (preliminary)

> This is the discovery agent's best guess at TC structure. The architecture
> agent will refine this into the actual epic/TC/issue plan.

| TC | Tentative Name | Responsibilities | Estimated Size |
|----|---------------|------------------|----------------|
| TC-A | [Name] | [What it does] | S/M/L |
| TC-B | [Name] | [What it does] | S/M/L |

## 11. Handoff Notes for Architecture Agent

[Any additional context, concerns, or suggestions for the architecture agent.
Reference V_MODEL_FRAMEWORK.md for process details.]
```
