# TC-B-00: Stream + Settings — Component Definition

> **Epic**: E-002 Crafter Chat UI (`../EPIC_002_CRAFTER_CHAT_UI.md`)
> **V-Model**: SWE1-B (derived from SYS1-002)
> **Requirements**: SW-REQ-STREAM
> **Review Mode**: no-reviews (impl self-verifies per STEP E-NR; no reviewer is spawned)
> **Status**: ✅ Complete
> **Last Updated**: 2026-10-12

---

## Component Goal

SSE streaming into the chat thread, picture input to the AI, and the settings surface: Scaico
connection (per-user key + team select), `contact@swaibian.com` mailto fallback, LiteLLM direct
mode toggle, and gateway endpoint config. This is stories #2–#6 made real.

## Responsibilities

1. **Streaming** — SSE stream rendering into thread + toolcall view (Scaico `send_task_stream`
   pattern; LiteLLM direct path).
2. **Picture input** — image send pipeline (upload/resize/serving, epic 005 pattern).
3. **Settings** — Scaico key + team select, mailto CTA, LiteLLM direct toggle, endpoint config.

## Logging & Observability Allocation (mandatory cross-cutting)

Instrument stream lifecycle, image pipeline, settings changes. Never log keys, prompts, image
data, or message content. TC-B-01 instruments; TC-B-02 (closer) verifies redaction.

## Integration Points

| Direction | Component | Interface |
|:----------|:----------|:----------|
| **Uses** | TC-A chat thread | Stream target + toolcall view |
| **Uses** | Scaico API | Per-user key, team select, `send_task_stream` SSE |
| **Uses** | LiteLLM proxy | Direct mode completions |
| **Provides to** | TC-C packaging | Settings + streaming to ship |

## Runtime Instantiation Map

| Component Class | Instantiated In | Lifecycle Owner | Route / Tool / Export Path |
|:----------------|:----------------|:----------------|:---------------------------|
| Stream hook | `view/src/.../useChatStream.ts` | chat thread | SSE subscription |
| Picture input | `view/src/.../PictureInput.tsx` | composer | upload pipeline |
| Settings view | `view/src/.../Settings.tsx` | router | `/crafter/settings` route |

> Rules: TC-B-01 owns streaming + pictures; TC-B-02 owns settings and verifies rows.

## Architecture References

| Artifact | Path | Relevance |
|----------|------|-----------|
| Component Overview | `project_management/architecture/diagrams/component-overview.md` | Stream + settings |
| API Contracts | `project_management/architecture/diagrams/api-contracts.md` | SSE + settings contracts |

## Key Files

| Action | File | Purpose |
|:-------|:-----|:--------|
| Create | `view/src/.../useChatStream.ts` | SSE streaming hook |
| Create | `view/src/.../PictureInput.tsx` | Image send |
| Create | `view/src/.../Settings.tsx` | Settings surface |
| Create | `view/src/.../*.test.tsx` | SWE4 view tests |

## Issues

| Issue | Title | Type | V-Model | Priority | Effort | Status |
|:------|:------|:-----|:--------|:---------|:-------|:-------|
| [TC-B-01](TC-B-01_STREAMING_AND_PICTURES.md) | SSE streaming + picture input | 🔨 Impl | SWE3-B-01 | P0-Critical | M | ✅ Complete |
| [TC-B-02](TC-B-02_SETTINGS_AND_CLOSER.md) | Settings (Scaico/LiteLLM) + TC closer | 🔨 Impl | SWE3-B-02 | P0-Critical | M | ✅ Complete |

## Acceptance Test Plan (SWE6)

| # | Acceptance Criterion | Test Type | Gate |
|---|---------------------|-----------|------|
| 1 | Streamed reply renders incrementally with toolcalls | Integration | 🔴 |
| 2 | Picture send → AI receives image (mocked) | Integration | 🔴 |
| 3 | Scaico key → team select populates; no key → mailto CTA + direct mode | Unit + Integration | 🔴 |

## Decisions Log

| Date | Decision | Rationale | ADR |
|:-----|:---------|:----------|:----|
| 2026-10-11 | SSE over WebSocket; controller-side LiteLLM | Discovery C1; proven pattern | — |

## Architecture Documentation Revisions

| Date | Issue | Changes Made |
|------|-------|-------------|
| — | — | (filled by TC-B-02 closer) |

---

*Shared context document — read before starting any TC-B issue, update after completing each one.*
