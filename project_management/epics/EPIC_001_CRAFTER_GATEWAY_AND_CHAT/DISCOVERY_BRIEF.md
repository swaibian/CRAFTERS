# Discovery Brief: Crafter Gateway + Chat UI (with Craft accessibility contributions)

**Date**: 2026-10-11
**Participants**: Product owner + swaibian-discovery agent
**Status**: ✅ Ready for Architecture

---

## 1. Problem Statement

The 12 storytold Craft apps (PhotoCraft, VectorCraft, FilmCraft, LightCraft, PdfCraft,
EffectCraft, DesignCraft, WordCraft, SoundCraft, DeckCraft, CADCraft, GridCraft) each expose
their full functionality to agents already (stdio MCP + loopback control channel + command
registry — see prior research in
`project_management/_templates/raw_Repository_findings/`). But there is **no connector and no
UI** that lets a normal user open a file, pick a tool, and chat with agents that work inside the
application: no unified visual/perception access, no streaming chat with toolcall view, no Scaico
team wiring, no local-or-containerised runnable app. Users must hand-assemble CLIs and MCP
configs per app. Without this, the Craft suite stays developer-only and the Scaico team
definitions in `Scaico_Teams/teams/` have nothing to connect to.

## 2. Agreed Scope

### In Scope

- **Part A — Craft accessibility contributions**: reference upstream PRs making 2 pilot apps
  100% agent-accessible (pdfcraft: AccessKit-via-MCP; photocraft: canvasRect synthesis), plus a
  documented contribution pattern for the remaining 10 (rollout deferred).
- **Part B — Crafter gateway service**: Python FastMCP gateway (stdio + streamable_http with
  bearer tokens + per-token tool allowlists) fronting the 12 app CLIs; Phase 1+2 tools from
  `08-REQUIRED-TOOLS.md` (`craft_apps`, `craft_status`, `craft_run`, `craft_run_tool`,
  `craft_app_call`, `craft_look`, `craft_snapshot`/`craft_restore`, `craft_record`,
  `craft_assert`); per-session filesystem roots; containerised local run.
- **Part C — Crafter Chat UI (web app)**: tool picker + drag/drop file input (opens in selected
  tool, enables chat about the file); chat with picture input to AI, streaming output, toolcall
  view, full markdown rendering (reuse `SharedChatSection.tsx` patterns); settings page with
  Scaico connection (per-user key + team select) and `contact@swaibian.com` mailto fallback when
  no access; reduced direct mode via controller-side LiteLLM proxy; Docker packaging (web first,
  Electron deferred).
- **Scaico wiring**: per-user API key, team select from the existing `craft_*` team JSONs,
  `send_task_stream` SSE reuse.

### Out of Scope

- 12-app accessibility rollout (deferred; pattern only).
- Session recording/replay + audit log (deferred H3).
- Cross-app pipeline templates (deferred H4).
- Shared MCP shell upstream to `craft-libs` (deferred H5).
- Electron shell (deferred; web + Docker first).
- Cloud `artcraft-services` generation integration (separate surface, not this epic).

### Open Questions (unresolved)

- Exact upstream PR acceptance process per Craft repo (maintainer response unknown).
- Whether `deckcraft call_app` can shortcut cross-app work (traced as research, not blocking).

## 3. User Stories / Use Cases

| # | As a...         | I want to...                                                        | So that...                                  | Priority |
|---|-----------------|---------------------------------------------------------------------|---------------------------------------------|----------|
| 1 | Designer        | drag a PSD onto the chat, pick PhotoCraft, and ask for edits        | the agent works in the real app on my file  | P0       |
| 2 | Designer        | see streamed replies with tool calls + rendered markdown            | I can follow and trust what the agent does  | P0       |
| 3 | Designer        | send a picture to the AI mid-chat                                   | I can point at visual problems              | P0       |
| 4 | Team lead       | connect my Scaico key and pick a craft team                         | agents run under my team with my budget     | P0       |
| 5 | Evaluator       | request Scaico access via contact@swaibian.com link                 | I can get access without a dead end         | P1       |
| 6 | Privacy user    | run fully local (container) with direct LiteLLM mode, no Scaico     | nothing leaves my machine except LLM calls  | P0       |
| 7 | Agent developer | call one gateway tool per app + discovery, with snapshots/asserts   | agents can't silently corrupt documents     | P0       |
| 8 | Maintainer      | apply the accessibility contribution pattern to a new Craft app      | all 12 apps become 100% agent-accessible    | P1       |

## 4. Technology Decisions

| Decision         | Choice                                                        | Rationale                                              | Alternatives Considered      |
|------------------|---------------------------------------------------------------|--------------------------------------------------------|------------------------------|
| Gateway stack    | Python FastMCP service                                        | Mirrors swaibian-one `src/mcp/main.py`; reuses auth/catalog | Rust (like Craft apps), TS sidecar |
| Gateway transports | stdio + streamable_http w/ bearer + allowlists              | Scaico team format requires streamable_http            | stdio only (insufficient)    |
| LLM integration  | Controller-side LiteLLM proxy                                 | Keys server-side, per-user budgets                     | View-side direct (leaks keys) |
| Chat UI          | React/Vite, reuse SharedChatSection patterns                  | react-markdown+GFM/KaTeX, toolcall blocks, working pill exist | New chat stack (waste)      |
| Streaming        | SSE via `send_task_stream` pattern                            | Proven in scaico_client.py                             | WebSocket (heavier)          |
| Packaging        | Web app + Docker first; Electron later                        | Matches swaibian-one deploy/ + scaico compose          | Electron day one (slower)    |
| Pilot apps       | photocraft + pdfcraft + gridcraft                             | Cover raster, document, data; gateway generic for rest | All 12 at once (too much)    |
| Scaico auth      | Per-user key + team select; mailto fallback                   | Matches epic 003 patterns                              | Single global key (no isolation) |
| Containment      | Container + per-session roots                                 | 8/12 apps lack confinement                             | Trust local (unsafe)         |

## 5. UI / UX Requirements

- **Layout**: Left = tool picker + file dropzone/opened-file header; center = chat thread;
  right (collapsible) = toolcall detail view; top bar = connection status; settings = Scaico /
    LiteLLM / gateway endpoint.
- **Key interactions**: (1) select tool → (2) drag/drop file → file opens in tool, chat enables
  → (3) chat with text + picture input → (4) streamed markdown replies with inline toolcall
  blocks → (5) snapshot/restore + verify actions on agent edits. Settings: enter Scaico key →
  team dropdown populates; no key → mailto CTA + LiteLLM direct mode toggle.
- **Accessibility**: Keyboard-operable chat; alt text on rendered images; respects
  prefers-reduced-motion for streaming.
- **Responsive**: Desktop-first; usable tablet; mobile deferred.

## 6. Constraints & Risks

| Type      | Description                                              | Impact                         | Mitigation                                        |
|-----------|----------------------------------------------------------|--------------------------------|---------------------------------------------------|
| Technical | Upstream PRs may not be accepted                         | Part A stalls                  | Gateway synthesis fallback (A3); pattern still useful |
| Security  | 8/12 apps lack filesystem confinement                    | Agent file escape              | Container + per-session roots; snapshots          |
| Security  | Per-user Scaico keys + gateway bearer tokens             | Token leakage                  | Server-side storage, per-user denial tests, no token in logs |
| Performance | 12 servers × ~25 tools in context                      | Agent degradation              | Gateway allowlists; pilot 3 apps first            |
| Performance | Full-window screenshots at Retina DPI                  | Token blowup                   | Contact sheets + low-DPI defaults (H2)            |
| Scope     | Max 2 epics × 3 TCs × 2 issues                           | Must stay small                | Phase 1+2 tools only; defer H3–H5                 |

## 7. Existing Requirements Found

| Requirement | Title | Relevance |
|-------------|-------|-----------|
| (swaibian-one EPIC 003) | SCAICO integration (keys, meetings, chat client) | Reuse key validation, meeting links, `send_task_stream` |
| (swaibian-one EPIC 005) | Chat image support (upload/resize/serving/rendering) | Reuse picture-input pipeline |
| (swaibian-one EPIC 006) | Manual team management | Team select/attribute editing patterns |
| (swaibian-one EPIC 009) | LLM selection | LLM settings view patterns |
| (swaibian-one EPIC 028) | Services registry + MCP inspection | Service registry + agent assignment patterns |
| (raw findings 08) | REQUIRED-TOOLS Phase 1+2 | Pre-existing tool REQs for gateway |

*New REQ/SW-REQ needed for: Craft-specific gateway tools, accessibility PR contents, Crafter
settings (Scaico connect + mailto + LiteLLM direct), drag/drop file-open flow.*

## 8. Brainstorming Outcomes

### Accepted Ideas

- H1 Snapshot/restore + assert seatbelt: rollback + verification; core trust story.
- H2 Contact sheets: ~30× token saving on multi-page review.

### Rejected Ideas

- (none — scope controlled via size cap instead)

### Deferred Ideas (future consideration)

- H3 Session recording/replay + audit log.
- H4 Cross-app pipeline templates.
- H5 Shared MCP shell upstream to `craft-libs`.
- Electron shell (after web + Docker proves out).
- 12-app accessibility rollout (after 2-app reference pattern).

## 9. V-Model Scope Classification

| Aspect | Classification | Notes |
|--------|---------------|-------|
| System Impact | 🟡 Module | New connector app in Crafters; touches no swaibian-one code (reuse only) |
| Integration Scope | Multi-component | Gateway ↔ 12 CLIs; UI ↔ gateway ↔ Scaico/LiteLLM |
| Test Level Needed | SWE4+SWE5 | Unit per issue; integration on last issue of each TC (no-reviews: self-verify) |
| Architecture Docs Exist? | Partial | Raw findings 00–08 exist; no arch diagrams yet — first TC covers scaffold |
| Estimated Batch Count | 2 epics × 3 TCs × 2 issues = 12 issues, no SWE5 (no-reviews mode) | Matches requested cap |

## 10. Suggested Component Breakdown (preliminary)

| TC | Tentative Name | Responsibilities | Estimated Size |
|----|---------------|------------------|----------------|
| E1/TC-A | Gateway core + Phase-1 tools | FastMCP service, transports, allowlists, pilot wiring | M |
| E1/TC-B | Verification tools (Phase-2) + containment | look/snapshot/record/assert, roots, Docker | M |
| E1/TC-C | Accessibility reference PRs | pdfcraft AccessKit-via-MCP, photocraft canvasRect, pattern doc | S |
| E2/TC-A | Chat UI + file flow | Tool picker, drag/drop open, markdown + toolcall view | M |
| E2/TC-B | Streaming + picture input | SSE streaming, image send, settings/Scaico/LiteLLM | M |
| E2/TC-C | Packaging + Scaico teams | Docker compose, team select, mailto fallback, e2e | S |

## 11. Handoff Notes for Architecture Agent

- **Review Mode: no-reviews.** No SWE5 issues; every issue is SWE3, impl self-verifies; each
  TC's last issue is the closer. Max 2 epics, 3 TCs each, 2 issues each = 12 issues total.
- Target repo root: `05_Products/Crafters/project_management/epics/` (create `EPIC_OVERVIEW.md`
  there if missing). Do NOT write into swaibian-one.
- Prior research is the requirements base: `_templates/raw_Repository_findings/00–08` and
  `Scaico_Teams/teams/*.json`. Reuse swaibian-one code by reference only.
- Auth implications: per-user Scaico keys + gateway bearer tokens; every new endpoint/tool tests
  per-user denial, session isolation, no token leakage.
- Discovery decisions locked (owner-confirmed intent, recommendations accepted): A1, B1, C1, D1,
  E1, F1, G1; H1+H2 accepted; H3–H5 deferred.
