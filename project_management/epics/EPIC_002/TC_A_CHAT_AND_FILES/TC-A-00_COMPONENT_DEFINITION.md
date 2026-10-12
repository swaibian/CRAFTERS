# TC-A-00: Chat + Files — Component Definition

> **Epic**: E-002 Crafter Chat UI (`../EPIC_002_CRAFTER_CHAT_UI.md`)
> **V-Model**: SWE1-A (derived from SYS1-002)
> **Requirements**: SW-REQ-CHAT
> **Review Mode**: no-reviews (impl self-verifies per STEP E-NR; no reviewer is spawned)
> **Status**: ✅ Complete
> **Last Updated**: 2026-10-12

---

## Component Goal

The chat thread with tool picker, drag/drop file flow (file opens in the selected app, chat
enables about it), full markdown rendering and toolcall view. This is the core user-facing
surface: select tool → drop file → chat with verify actions.

## Responsibilities

1. **Tool picker + file flow** — app selection, drag/drop into session roots, open-in-app,
   chat enablement bound to the opened document.
2. **Chat thread** — markdown (GFM/KaTeX) rendering, inline toolcall blocks, working pill,
   snapshot/restore + verify actions on agent edits.
3. **Keyboard + a11y** — keyboard-operable chat, alt text on renders, reduced-motion respect.

## Logging & Observability Allocation (mandatory cross-cutting)

View-layer logging at chat/file-flow boundaries via the project logger; no `console.*` paths.
TC-A-01 instruments; TC-A-02 (closer) verifies wiring and redaction (no prompts, document
content, image data, or tokens in logs).

## Integration Points

| Direction | Component | Interface |
|:----------|:----------|:----------|
| **Uses** | EPIC_001 Gateway | Phase-1/2 tools, sessions, snapshots |
| **Uses** | swaibian-one patterns | SharedChatSection, chat-image pipeline (reference) |
| **Provides to** | TC-B streaming | Chat thread + toolcall view to stream into |
| **Provides to** | TC-C packaging | Runnable view service |

## Runtime Instantiation Map

| Component Class | Instantiated In | Lifecycle Owner | Route / Tool / Export Path |
|:----------------|:----------------|:----------------|:---------------------------|
| Chat thread view | `view/src/.../CrafterChat.tsx` | React router | `/crafter` route |
| Tool picker + dropzone | `view/src/.../ToolPicker.tsx` | chat view | chat header |
| Toolcall view | `view/src/.../ToolcallView.tsx` | chat message | inline + collapsible detail |

> Rules: TC-A-01 owns "wire into route" explicitly. TC-A-02 verifies every row.

## Architecture References

| Artifact | Path | Relevance |
|----------|------|-----------|
| Component Overview | `project_management/architecture/diagrams/component-overview.md` | Chat UI block |
| Flows | `project_management/architecture/diagrams/flow-chat-file-open.md` | File-open flow |
| API Contracts | `project_management/architecture/diagrams/api-contracts.md` | Chat contracts |

## Key Files

| Action | File | Purpose |
|:-------|:-----|:--------|
| Create | `view/src/.../CrafterChat.tsx` | Chat thread |
| Create | `view/src/.../ToolPicker.tsx` | Tool picker + dropzone |
| Create | `view/src/.../ToolcallView.tsx` | Toolcall rendering |
| Create | `view/src/.../*.test.tsx` | SWE4 view tests |

## Issues

| Issue | Title | Type | V-Model | Priority | Effort | Status |
|:------|:------|:-----|:--------|:---------|:-------|:-------|
| [TC-A-01](TC-A-01_CHAT_THREAD_AND_FILES.md) | Chat thread + tool picker + file flow | 🔨 Impl | SWE3-A-01 | P0-Critical | M | ✅ Complete |
| [TC-A-02](TC-A-02_TOOLCALL_VIEW_AND_CLOSER.md) | Toolcall view + verify actions + TC closer | 🔨 Impl | SWE3-A-02 | P0-Critical | M | ✅ Complete |

## Acceptance Test Plan (SWE6)

| # | Acceptance Criterion | Test Type | Gate |
|---|---------------------|-----------|------|
| 1 | Drop file → opens in selected app → chat enables (pilot) | Integration | 🔴 |
| 2 | Markdown + toolcalls render; keyboard operable | Unit + Integration | 🔴 |
| 3 | Snapshot/restore + verify actions work on agent edits | Integration | 🔴 |

## Decisions Log

| Date | Decision | Rationale | ADR |
|:-----|:---------|:----------|:----|
| 2026-10-11 | Reuse SharedChatSection patterns | Markdown/toolcall/working pill exist | — |

## Architecture Documentation Revisions

| Date | Issue | Changes Made |
|------|-------|-------------|
| — | — | (filled by TC-A-02 closer) |

---

*Shared context document — read before starting any TC-A issue, update after completing each one.*
