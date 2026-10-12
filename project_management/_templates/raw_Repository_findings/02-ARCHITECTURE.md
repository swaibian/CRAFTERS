# 02 — Architecture & Gateway Design

Companion to `01-RESEARCH-FINDINGS.md`. This document covers (a) why the existing design is what
it is, (b) the wrapper/gateway architecture to build on top of it.

---

## Part 1 — Patterns found across all 12 apps

Seven patterns recur. Recognising them is what makes a wrapper tractable.

### Pattern 1 — Command registry as the single source of truth

Every app: `crates/engine/src/cmd*` holds every user-visible action as
`(id, label, menu_path, shortcut, param_schema_doc, enabled_fn)`. Menus, shortcuts, gestures,
CLI, control channel and MCP all dispatch into it.

- **Discovery:** `command_list` / `list_commands` / `engine.commands`
- **Invocation:** `command_run` / `execute` / `engine.execute`
- **Batching:** `command_batch` / `batch` — with `$N.path` / `$last.path` references into earlier
  step results and `"$$"` escaping (`"${N.path}"` interpolates into longer strings)

**Implication for a wrapper:** the universal tool shape is
`{ app, id, params }`. One generic schema covers ~1,000 capabilities per app. You never need to
enumerate features.

### Pattern 2 — Two backends behind one tool surface

Every app's MCP server is a thin protocol shell over a `Backend` trait:

| Backend | What it is | How selected |
|---|---|---|
| `Headless` | in-process `engine::Session`, CPU renderer, no window | default, or `--headless` |
| `Remote` / `Bridge` | TCP client to `<app> --control PORT` | `--connect PORT` / `--bridge HOST:PORT` |

The headless backend **implements the same control-channel method names itself**. This is
deliberate: the headless path is a faithful simulation of the GUI path, so an agent's script
behaves identically either way.

**Headless is what you want by default.** No window, no GPU, no display server, instant startup,
deterministic. Bridge only when a human needs to watch or intervene.

### Pattern 3 — Three-tier tool surface

```text
Tier 1  APP_ONLY / ui_* / screenshot     live-window control: clicks, keys, dialogs, window PNG
Tier 2  domain tools                      ergonomic app verbs: draw_shape, set_cell, add_slide
Tier 3  command_list + run_command        universal escape hatch: every command in the registry
```

Tier 3 means **no functionality is gated behind a missing Tier-2 tool**. If your gateway only
exposes Tier 3, you lose nothing in capability — only in ergonomics.

### Pattern 4 — Capability-scoped filesystem roots

Apps that sandbox accept read and write roots **independently** at launch
(`--automation-read-root`, `--automation-write-root`, or `--root`). Paths must be relative to the
root or absolute-but-beneath-it. Rejected before any file effect: absolute paths outside the root,
`..` traversal, alternate separators in relative paths, drive/device/stream prefixes, malformed
components, symlink escapes. Read and write authority are independent; a new output file's parent
must already exist.

**Not universal.** FilmCraft has none. PdfCraft uses a single `--root`. CadCraft/GridCraft/
DeckCraft/WordCraft/SoundCraft use `--connect` and sandbox only if the app does. Audit per app
(`04-SECURITY.md`).

### Pattern 5 — Ambient-path commands are refused to automation

PhotoCraft's rule, and the model the others follow: any command that reads or writes a file by an
ambient path rather than through the capability interface is refused with

> `automation command '<id>' uses ambient filesystem paths and is disabled; use
> capability-scoped document methods`

So `file.open` / `file.save` / `file.saveAs` fail; use `app.open` / `app.save`. Preferences
updates that could indirectly grant filesystem access (`colorSettings`, `scriptEvents`,
`historyLog`, `plugIns`, `scratchDisks`) are refused too. Smart Objects that need a disk read
stay refused, but in-memory edit-contents/convert-to-layers work.

This is a genuine capability ceiling for automation, not a bug. Know it.

### Pattern 6 — Background jobs and cancellation

Long commands are async jobs with progress. MCP progress uses `_meta.progressToken`; notifications
increase strictly, are throttled to ≤10/s except completion, and include `total`. Cancellation is
`notifications/cancelled {requestId}` and stops at a frame boundary. **Ping stays responsive
during a render.** PhotoCraft's scoped render-video writer refuses to overwrite an existing
target and only removes files that job created.

### Pattern 7 — Context-aware protocol surface

Both families implement the 2026-07-28 revision and emit `resultType: "complete"`,
`ttlMs`, `cacheScope: "private"` on catalogs, with `ttlMs: 0` for reads. Clients that negotiated
the older revision get a plain response. This is how the apps already cope with tool-list size —
**and it is the mechanism your gateway should reuse.**

---

## Part 2 — Why a raw "12 servers in one config" approach fails

> **⚠️ SUPERSEDED IN PART — see `07-SCAICO-TEAMS.md`.**
> The tool-count argument below is right *only if one agent sees all 270 tools*. Your Scaico team
> format assigns each agent an explicit `tools: [...]` allowlist, so each specialist sees 8–20
> tools and the full surface stays addressable. **Per-agent allowlists, not a single flattened
> gateway, are the primary architecture.** The gateway's tool surface (§3.3) should be flat and
> small so that allowlists compose cleanly against it.
>
> Also: §3.1 recommends **stdio only**. The Scaico format uses
> `"transport": "streamable_http"`, and all 12 app servers are stdio-only. **Build dual transport
> from day one** — stdio for local agents, streamable-HTTP with bearer tokens and per-token
> allowlists for Scaico. The latter is a multi-tenant server and needs its own threat model.

The practical blocker is context, not capability.

| Metric | Value |
|---|---|
| Servers | 12 |
| Curated tools each | 15–35 (mean ≈ 22) |
| **Total tool definitions** | **≈ 270** |
| Tool schemas in tokens | ≈ 60–120 k tokens before any user prompt |
| Typical agent-client practical ceiling | 40–80 tools |

Consequences: tool selection degrades (models pick the wrong `execute`/`list_commands`/`click`),
system prompts get truncated or evicted, and several of the apps have **identical tool names**
(`list_commands`, `execute`, `run_command`, `batch`, `screenshot`, `ui_inspect`, `click`, `key`,
`type_text`, `pointer`, `parity`, `new_document`, `open_document`, `save_document`,
`inspect_document`, `render_page`). Unprefixed, those are ambiguous and the model will guess
wrong.

Two of the apps already solve this internally, and you should copy them:

- **PdfCraft `--compact`** — 5 tools (`command_list`, `command_run`, `command_batch`,
  `doc_inspect`, `render_preview`) plus `tool_search` / `tool_call`. The whole app behind five
  verbs.
- **SoundCraft** — 17 tools total, `list_commands` + `execute` + `batch` doing the heavy lifting.

---

## Part 3 — The recommended architecture: `crafters-gateway`

### 3.1 Shape

```text
┌──────────────────────────────────────────────────────────────────┐
│                      Agent (Claude Code, etc.)                  │
└───────────────────────────────┬──────────────────────────────────┘
                                │ stdio, MCP
┌───────────────────────────────▼──────────────────────────────────┐
│                        crafters-gateway                          │
│                                                                  │
│  MCP server (Rust, rmcp)                                          │
│    • 12 static tools:  photo, vector, film, light, pdf, effect,  │
│      design, word, deck, grid, cad, sound, artcraft_cloud        │
│    • 3 meta tools: craft_apps, craft_tools, craft_call            │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ AppBackend (trait) — one impl per family                    │  │
│  │  • spawn(StdioMcpBackend)  process per app, lazy            │  │
│  │  • ControlChannelBackend    TCP client for bridge mode      │  │
│  └────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Policy: per-app root confinement, allowlists, budgets       │  │
│  └────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Liveness: idle timeout, crash restart, per-app state        │  │
│  └────────────────────────────────────────────────────────────┘  │
└───────┬────────────┬────────────┬─────────────┬──────────────────┘
        │            │            │             │
   photocraft-cli  vectorcraft-  filmcraft-cli   …        api.storyteller.ai
        mcp        craft-cli mcp mcp                        (REST, see doc 03)
```

### 3.2 Why stdio, not a network server

Each app's MCP server is stdio. Your gateway is the process that owns those pipes. Spawn them as
child processes with `tokio::process::Command`, speak MCP to each. Do **not** try to convert them
to HTTP — you would lose the binary's framing, its stderr logs and its lifecycle management for
no benefit.

The gateway itself should also be stdio. That keeps the agent config a single entry
(`"command": "crafters-gateway"`), inherits the client's process supervision, and means no port
and no auth surface for the gateway itself.

### 3.3 The tool surface

**12 app tools**, deliberately boring and symmetric:

```rust
/// app: "photocraft" | "vectorcraft" | … (enum, not free string)
photo(app: App, action: String, params: Value) -> ToolResult
```

Rationale for one generic shape rather than 12 bespoke schemas:

- Identical schema → the agent's prompt is tiny and stable.
- The app enum prevents cross-app name guessing.
- Adding a 13th app later is a one-line enum change.
- Cost: less self-documenting. Mitigate with a strong `INSTRUCTIONS` string and the `craft_tools`
  discovery tool, exactly as the apps themselves do.

**Plus 3 meta tools:**

| Tool | Purpose |
|---|---|
| `craft_apps {include?, filter?}` | List apps, what each is good at, availability, whether its server is running, its control address |
| `craft_tools {app, filter?, detail?}` | Proxy `tools/list` from the app's MCP server, optionally filtered. This is how the agent discovers an app's ergonomic tools without paying for them up front |
| `craft_call {app, method, params}` | Raw passthrough to the control-protocol methods (`ui.inspect`, `ui.set`, `app.open`, `jobs.list`, …) for anything the curated tools don't cover |

**`craft_call` is the escape hatch that makes this design future-proof.** When an app ships a new
control method, you expose it the same day with no gateway change.

### 3.4 Two call paths per app

```text
Tier A (default)  headless MCP child process        no window, no GPU, instant, deterministic
Tier B (opt-in)   --connect PORT / --bridge HOST:PORT  live GUI, screenshots, synthetic input
```

Switch per app at gateway start, and per call via a `mode` parameter on the app tool. Keep a
single running instance per (app, mode) — do not respawn per call.

### 3.5 Process lifecycle

| Concern | Policy |
|---|---|
| Spawn | Lazy, on first use for that app |
| Idle | Terminate headless children after N minutes idle (default 10); persist nothing |
| Bridge | Never auto-spawn the GUI. Require the user to have started it; probe on demand |
| Crash | Detect EOF on stdout; restart up to 3×; report the restart to the agent |
| Timeout | Per-call, default 60 s; long jobs return `{job, pending}` instead of blocking |
| Cancellation | Forward MCP `notifications/cancelled` to the child |
| stderr | Capture to a per-app log file; surface the last N lines on crash |

**Do not auto-retry writes.** PhotoCraft's own bridge refuses to: a transport failure mid-request
may mean the edit landed. Retry only pure reads.

### 3.6 Sandboxing

Compose roots per app at launch:

```rust
struct AppConfig {
    binary:           PathBuf,          // e.g. /usr/local/bin/photocraft-cli
    mode:             Mode,             // Headless | Bridge(addr)
    read_root:        Option<PathBuf>,  // None => UNSANDBOXED, refuse by default
    write_root:       Option<PathBuf>,
    read_only:        bool,
    max_memory_mb:    Option<u64>,      // a guard, not a limit the apps enforce
}
```

Defaults must be **sandboxed**. FilmCraft and the other apps with no confinement flags should
default to `read_only: true` or be refused unless the operator opts in explicitly.

### 3.7 Cross-app workflows (Layer 2)

Implement as gateway tools that call several apps. High-value examples grounded in what the apps
actually expose:

| Workflow | Calls |
|---|---|
| `mockup` | designcraft (layout) → photocraft (retouch) → deckcraft (slide) → pdfcraft (export) |
| `asset_thumbnail` | any app → render_preview → shared asset store |
| `catalog_batch` | pdfcraft (source docs) → wordcraft (text extract) → gridcraft (index) |
| `color_pipeline` | lightcraft (develop RAW) → photocraft (grade) → deckcraft/pdfcraft (deliver) |
| `storyboard` | wordcraft (script) → designcraft/photocraft (frames) → filmcraft (assemble) |
| `musicbed` | soundcraft (mix) → filmcraft (score) |

Keep these as thin orchestration in the gateway. Do **not** fork the engines.

### 3.8 A shared asset namespace

The apps have no shared file store. Introduce one in the gateway:

- Every app gets the same `write_root` pointing at a per-session asset directory.
- `asset_put {path, from_app, kind}` / `asset_get {path}` / `asset_list {kind?}` move bytes
  between apps and record provenance (which app, which tool call, when).
- Provenance is what makes agent-generated work reviewable later.

---

## Part 4 — Alternative: contribute upstream

Worth evaluating before you build the gateway yourself.

**Upstream-friendly changes** (no forking, real value to the org):
- Add `crates/mcp` (or `automation`) to photocraft's siblings so all 12 are uniform.
- Extract the duplicated MCP shell (framing, `handle_line`, panic guard, logging queue,
  protocol-version negotiation) into `craft-libs` as a shared `craft-mcp` crate. Today it is
  copy-pasted 7 times in family B. A shared crate with a `Backend` trait would collapse ~4,500
  duplicated lines.
- Add `--automation-read-root`/`--automation-write-root` to FilmCraft and the other
  unconfined apps.
- Standardise tool-name namespacing (`photocraft_doc_inspect` vs `wordcraft_doc_inspect`) — or
  document the collisions.

**Not worth upstreaming:** a cross-app gateway is Storytold's product decision, not a library
concern. Build it yourself.

---

## Part 5 — Decision matrix

| Option | Effort | Capability | Context cost | Robustness | Verdict |
|---|---|---|---|---|---|
| Register all 12 servers directly | ~1 h | 100% | ~270 tools — too many | Per-process isolation, good | **Start here to validate** |
| Gateway with 12+3 tools | ~3–5 days | 100% | 15 tools | You own lifecycle/policy | **Recommended** |
| Gateway + cross-app workflows | +1–2 weeks | 100% + new | 15–30 tools | Same | Phase 2 |
| Per-feature wrappers (e.g. one tool per Photoshop filter) | Months | <100% | Thousands | Poor | **Do not do** — Tier 3 already covers it |
| Contribute `craft-mcp` to `craft-libs` | ~1 week | n/a | n/a | Removes 4.5k dup lines | Good parallel PR |

---

## Part 6 — Build order

1. **Validate.** Register 2–3 apps directly with your client. Confirm headless MCP works for the
   apps you care about; confirm which have usable confinement flags.
2. **Skeleton gateway.** `rmcp` server, one generic app tool + `craft_apps`, stdio child-process
   backend, one app working (start with GridCraft or SoundCraft — smallest surfaces). No policy,
   no lifecycle yet.
3. **Fan out.** All 12. Two backends (family A and family B) so you have proven the abstraction.
4. **Lifecycle.** Idle timeout, crash restart, per-call timeout, cancellation forwarding.
5. **Policy.** Roots, allowlists, budgets. Default-deny.
6. **Context.** `craft_tools` discovery + a `craft_instructions` tool, so the agent self-orients
   instead of carrying schemas.
7. **Bridge mode.** TCP control channel to the live GUIs, with correct no-auto-retry semantics.
8. **Cross-app workflows + asset namespace.**

Ship each step working. Steps 2–4 are a small amount of Rust; the research is done.