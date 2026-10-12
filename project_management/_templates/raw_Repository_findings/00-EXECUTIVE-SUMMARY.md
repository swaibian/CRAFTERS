# Crafters — Agent Integration: Executive Summary

**Date:** 2026-10-11
**Scope:** All 12 `storytold/craft*` applications in <https://github.com/storytold>
**Question asked:** How can every functionality of these tools be made available to AI agents?

---

## The headline finding

> **You do not need to build wrappers. Every single one of the 12 Craft apps already ships a
> first-class MCP (Model Context Protocol) server, a CLI with JSON batch scripting, and a
> token-authenticated loopback control channel to the live desktop app.**

This was not obvious from the outside and is not advertised on the GitHub landing pages. It is
documented per-repo (`docs/mcp.md`, `docs/control-protocol.md`) and implemented in every repo.

| What you wanted | What exists | Where |
|---|---|---|
| Wrapper around each tool's functionality | A native MCP server per app | `<app>-cli mcp` |
| REST-like API | JSON-lines control protocol over TCP | `<app> --control <port>` |
| REST-ish API (hosted) | Full Actix-web REST API for the cloud AI services | `storytold/artcraft-services` |
| "Every functionality exposed" | Every engine command is an MCP tool via a generic `run_command` | `command_list` + `run_command` |

**The most important architectural fact:** each app's entire user-visible surface is already
modelled as a **flat registry of engine commands with stable string ids and JSON params**.
Menus, keyboard shortcuts, panel gestures, the CLI, the control channel and MCP all funnel into
that same registry. That means `command_list` + `run_command` gives an agent 100% of an app's
functionality, not a hand-curated subset. The curated MCP tools on top (25–35 per app) are
ergonomic sugar, not the actual capability ceiling.

---

## Numbers

| Metric | Value |
|---|---|
| Craft apps analysed | 12 |
| Apps with a native MCP server | **12 / 12** |
| Apps with a loopback control channel to the live GUI | 12 / 12 |
| Apps with a headless CLI scripting surface | 12 / 12 |
| Apps with `docs/mcp.md` + `docs/control-protocol.md` | 12 / 12 |
| Distinct MCP tools exposed (curated) | ~270 across all apps |
| Approximate engine commands reachable per app | ~7,000 total; ~1,100 in FilmCraft/PhotoCraft |
| Hosted REST endpoints found (ArtCraft cloud) | ~250 routes, 3 generation surfaces |
| MCP SDK used | Official Rust SDK (`rmcp`) in 2 apps; hand-written JSON-RPC in 10 |

---

## Two integration families (important for your design)

The 12 apps are **not** uniform. They split into two implementations, and your wrapper must
handle both:

| Family | Apps | Implementation | MCP SDK | Session model |
|---|---|---|---|---|
| **A — "automation"** | photocraft, filmcraft, effectcraft, pdfcraft, soundcraft | `crates/automation` | `rmcp` (official, async/Tokio) for photocraft+filmcraft; hand-rolled for the rest | Headless + **Bridge** (`--bridge HOST:PORT`) |
| **B — "mcp"** | vectorcraft, lightcraft, designcraft, gridcraft, cadcraft, deckcraft, wordcraft | `crates/mcp` | Hand-written newline-delimited JSON-RPC 2.0, no async runtime | Headless + **Remote** (`--connect HOST:PORT`) |

Both speak standard MCP over stdio and both negotiate the same protocol revisions
(`2026-07-28`, `2025-06-18`, `2025-03-26`, `2024-11-05`). **A generic MCP client (Claude Code,
Cursor, opencode, …) can consume either unchanged.** The difference only matters if you build
your own aggregator.

---

## What you should actually build

Three layers, in increasing order of effort and payoff. See the other documents for detail.

### Layer 0 — Do nothing clever (recommended starting point, ~1 hour)

Register all 12 app MCP servers directly with your agent client. They are already stdio MCP
servers. Zero wrapper code.

```json
{
  "mcpServers": {
    "photocraft":   { "command": "photocraft-cli",   "args": ["mcp"] },
    "vectorcraft":  { "command": "vectorcraft-cli",  "args": ["mcp"] },
    "filmcraft":    { "command": "filmcraft-cli",    "args": ["mcp", "--demo"] }
  }
}
```

**Caveat:** 12 servers × ~25 tools = ~270 tool definitions in the agent's context. Most clients
degrade badly past ~40–80 tools. This is the real problem to solve, not "how do I call Photoshop".

### Layer 1 — A routing/aggregation MCP gateway (the recommended build)

A single stdio MCP server that exposes **12 logical tools** — one per app — and lazily proxies to
the right app's `mcp` process. Details in `02-ARCHITECTURE.md`.

```
Agent  ──►  crafters-gateway (1 MCP server, 12 tools + search)
              ├─► photocraft-cli mcp        (headless or --bridge)
              ├─► vectorcraft-cli mcp       …
              └─► …
```

Why this is the right shape:

- **Context-efficient.** The agent sees 12 tool schemas, not 270. Each app's full tool list is
  fetched on demand via a `craft_tools` discovery tool.
- **Zero protocol duplication.** The gateway speaks MCP *client* side to the apps; you inherit
  their schemas, annotations, resources and prompts verbatim.
- **Process-lifecycle management.** Spawning, idle-timeouts, crash-restart and per-app working
  directories become your problem, not the agent's.
- **Uniform sandboxing.** You can pin `--root`/`--automation-read-root` centrally.

### Layer 2 — Cross-app workflow tools (only after Layer 1 works)

Composites that span apps: "mockup workflow" (designcraft layout → photocraft retouch →
deckcraft slide → pdfcraft export), a shared `asset://` store, batch pipelines. Implement these
*in* the gateway as tools that call several apps.

---

## Risks and open questions

| Risk | Assessment |
|---|---|
| Tool-count blowup in agent context | **High, and unavoidable at Layer 0.** Solved by the gateway. |
| Two MCP implementations (family A / B) | Low. Both are conforming stdio MCP; the gateway is agnostic. |
| No filesystem confinement on some apps | **Real.** FilmCraft explicitly has *no* `--automation-read-root`; WordCraft/GridCraft differ again. Audit per app before exposing to an untrusted agent. See `04-SECURITY.md`. |
| Control channel is bearer-token only, unencrypted, loopback-only | Documented and intentional upstream. Do not tunnel it. |
| Two of the 12 repos are older/stubbier (cadcraft: 15 tools, 134 commands) | Tool counts vary 15–35; capability depth varies much more. |
| No cross-app orchestrator exists upstream | Confirmed absent. This is your differentiator. |

---

## Where the evidence is

Every claim above is backed by a file path in:

| Document | Contents |
|---|---|
| `01-RESEARCH-FINDINGS.md` | Per-app deep dive: tools, commands, control protocol, CLI flags, ports |
| `02-ARCHITECTURE.md` | The shared patterns, why the design is what it is, gateway design |
| `03-ARTCRAFT-CLOUD-API.md` | The hosted REST API (ArtCraft cloud AI) — a second, separate integration surface |
| `04-SECURITY.md` | Sandbox models, token handling, the actual threat surface |
| `05-QUICKSTART.md` | Copy-pasteable config to get running today |
| `SOURCES.md` | Every repo URL, file path and doc link consulted |

---

## The one-paragraph answer

Every Craft app is built around a command registry where each command has a stable id and JSON
params, and every app exposes that registry through three interchangeable transports: a stdio MCP
server (`<app>-cli mcp`), a token-authenticated loopback TCP JSON-lines channel to the live GUI
(`<app> --control <port>`), and a CLI for batch scripting. So "make every functionality available
to agents" is already solved per-app — what is missing is (a) a way for an agent to hold 12 of
these servers without drowning in ~270 tool schemas, and (b) cross-app workflows. Build one
gateway MCP server that fans out to the 12 existing servers, expose one tool per app plus a
discovery tool, and add cross-app composites on top. Do not write per-tool wrappers; there is
nothing left to wrap.