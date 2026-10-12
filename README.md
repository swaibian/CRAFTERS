# Crafters — Agent Integration Workspace

Research and design notes for exposing the full functionality of the
[`storytold`](https://github.com/storytold) **Craft Apps** (PhotoCraft, VectorCraft, FilmCraft,
LightCraft, PdfCraft, EffectCraft, DesignCraft, WordCraft, DeckCraft, GridCraft, CADCraft,
SoundCraft) to AI agents.

**Status:** research complete, nothing built yet.
**Research date:** 2026-10-11.

---

## Read in this order

| # | File | What you get |
|---|---|---|
| 00 | [00-EXECUTIVE-SUMMARY.md](00-EXECUTIVE-SUMMARY.md) | The answer in one page. Start here. |
| 01 | [01-RESEARCH-FINDINGS.md](01-RESEARCH-FINDINGS.md) | Per-app deep dive: every tool, every flag, every port |
| 02 | [02-ARCHITECTURE.md](02-ARCHITECTURE.md) | The patterns, and the gateway design to build |
| 03 | [03-ARTCRAFT-CLOUD-API.md](03-ARTCRAFT-CLOUD-API.md) | The hosted REST API (a separate surface) |
| 04 | [04-SECURITY.md](04-SECURITY.md) | Sandboxing, tokens, the real risk surface |
| 05 | [05-QUICKSTART.md](05-QUICKSTART.md) | Copy-pasteable configs that work today |
| **06** | **[06-PERCEPTION.md](06-PERCEPTION.md)** | **How an agent "sees" — three tiers, MCP resources, and the gaps** |
| **07** | **[07-SCAICO-TEAMS.md](07-SCAICO-TEAMS.md)** | **Agentic team design for creative work, in your team's schema** |
| **08** | **[08-REQUIRED-TOOLS.md](08-REQUIRED-TOOLS.md)** | **The ~24 tools the gateway must add, prioritized** |
| — | [SOURCES.md](SOURCES.md) | Every file path consulted, plus what could not be verified |

---

## The finding, in one paragraph

Every one of the 12 apps already ships a native MCP server (`<app>-cli mcp`), a loopback
JSON-lines control channel to the live GUI (`<app> --control <port>`), and a batch CLI. Each app
models its entire user-visible surface as a **command registry** with stable ids and JSON params,
and all three transports dispatch into it. So "make every functionality available to agents" is
**already solved per-app** — `command_list` + `run_command` reaches ~1,000 capabilities in
FilmCraft and PhotoCraft alone. What is missing is **observation over time, verification, and
accountability** — nothing diffs two states, nothing tells an agent it changed, nothing lets an
agent assert an edit worked without eyeballing pixels, and nothing proves a claim was measured
rather than invented. Those gaps are what a gateway has to build. See `08-REQUIRED-TOOLS.md`.

## Three things worth knowing before you start

1. **Per-agent tool allowlists dissolve the context problem.** My initial concern that 270 tools
   would overwhelm an agent assumed one agent sees all of them. Your Scaico format gives each agent
   an explicit `tools: [...]` list — each specialist sees 8–20 tools, and the full surface stays
   addressable. That is the right architecture, not a fallback.
2. **The apps are stdio-only MCP. Scaico needs `streamable_http`.** All twelve, zero exceptions.
   A gateway in front is mandatory, and it must speak HTTP with bearer tokens and per-token tool
   allowlists. This is a multi-tenant server, not a local one.
3. **Eight of twelve apps have no filesystem confinement.** FilmCraft says so explicitly. See
   `04-SECURITY.md` before running untrusted agents.

## Next steps

1. Read `00-EXECUTIVE-SUMMARY.md`, then apply two apps from `05-QUICKSTART.md` to your agent
   client and confirm headless MCP works.
2. Install the CLIs (release packages ship them; on macOS they are a separate zip asset).
3. Read `06-PERCEPTION.md` — it will change what you ask the agents to do.
4. Build Phase 1 and Phase 2 from `08-REQUIRED-TOOLS.md`. Phase 2 (`craft_look` +
   `craft_snapshot` + `craft_record` + `craft_assert`) is where the agent stops being able to lie
   about what it did.
5. Trace `deckcraft`'s `call_app` tool (`01-RESEARCH-FINDINGS.md` §7). If one Craft app can
   already call another, the gateway is partly built.

## Directory

```text
Crafters/
├── 00-EXECUTIVE-SUMMARY.md
├── 01-RESEARCH-FINDINGS.md
├── 02-ARCHITECTURE.md
├── 03-ARTCRAFT-CLOUD-API.md
├── 04-SECURITY.md
├── 05-QUICKSTART.md
├── 06-PERCEPTION.md
├── 07-SCAICO-TEAMS.md
├── 08-REQUIRED-TOOLS.md
└── SOURCES.md
```