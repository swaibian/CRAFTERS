# Completion Report Template

> Copy this template when creating `TC-X-YY_COMPLETION_REPORT.md`.
> Create this file alongside the issue file. Fill it in as work progresses.
> This is the **handoff document** — the next team reads this before starting.
>
> **Structure note**: This template reflects the proven format from TC-A/B/C.
> Sections are numbered for consistency across all completion reports.

---

```markdown
# TC-X-YY: [Issue Title] — Completion Report

**Issue**: TC-X-YY
**Component**: [Component Name]
**V-Model**: SWE3-X-YY
**Type**: 🔨 IMPLEMENTATION | 🔍 REVIEW
**Status**: ✅ COMPLETE
**Completed**: YYYY-MM-DD

---

## 1. What Was Built

### New Files

| File | Purpose |
|------|---------|
| `path/to/file.ext` | [What it does — be specific: interface, implementation, test, config] |

### Changed Files

| File | Change |
|------|--------|
| `path/to/file.ext` | [What changed and why] |

### APIs / Contracts Defined

**`path/to/module.ext`** — [module purpose]:
- `methodName(params): returnType` — [what it does]
- `anotherMethod()` — [what it does]

---

## 2. Key Decisions

| Decision | Rationale |
|----------|-----------|
| [What was decided] | [Why — reference ADR if created] |

---

## 3. Gate Results

| Gate | Result | Notes |
|------|--------|-------|
| Pre-check test suite (Task 0.2) | ✅ / ❌ | [Baseline: X/X passing, N files] |
| Post-implementation suite (Task N+1) | ✅ / ❌ | [X/X passing (Y new tests), N files] |
| Coverage vs baseline | ✅ / ❌ | [Not regressed / +X%] |
| Typecheck (SWE4-BUILD) | ✅ / ❌ | [0 errors / N errors — file:line details] |
| Lint (SWE4-LINT) | ✅ / ⚠️ | [0 errors, 0 warnings / N errors — categories] |
| Coverage vs target | ✅ / ⚠️ | [Target: X%, actual: Y%] |

> Gates marked ⏭️ SKIPPED must include a documented reason.

## 3.5 Logger Evidence (mandatory)

| Item | Evidence |
|------|----------|
| Event names and allow-listed fields | [List events or explain bounded N/A] |
| Request/user/session propagation | [Entry point → changed boundary → response/job path] |
| Redaction/no-secret tests | [Test paths and forbidden-field cases] |
| Sink and failure behavior | [Log sink/queue/fallback impact] |
| Audit/metrics separation | [How the streams remain distinct] |

---

## 4. Handoff for TC-X-{YY+1} ([Successor Title])

> **MUST be specific to what was built. Generic "add notes for successor" is NOT acceptable.**
> See HANDOVER_CHAIN_RULES.md Rule 3 for required content per work type.

**Entry point**: `path/to/start/here.ext` — [what the successor should do with it]

**What you inherit**:
- [API/module]: [what it provides, import path, usage example]
- [Contract/type]: [where it is, how to use it]

**What is NOT implemented yet** (leave as stubs):
- [Feature/module] — [which future issue owns it]

**Run tests**: `[exact test command]` from `[working directory]`

---

## ⚠️ Known Issues / Limitations (if any)

1. **[Issue Name]** — [Impact, workaround, future fix reference]

---

## Traceability

| Level | ID | Artifact |
|-------|-----|---------|
| SYS1 | SYS1-XXX | Epic: EPIC_XXX_NAME.md |
| SWE1 | SWE1-X | TC: TC-X-00_COMPONENT_DEFINITION.md |
| SWE3 | SWE3-X-YY | Issue: TC-X-YY_TITLE.md |
| SWE4 | — | Tests: [test file paths] |
```
