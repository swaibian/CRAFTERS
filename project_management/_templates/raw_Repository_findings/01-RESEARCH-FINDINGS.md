# 01 — Research Findings: Per-App Deep Dive

**Date of research:** 2026-10-11
**Method:** shallow clone of all 12 app repos + `craft-libs`, `craft-launcher`,
`craft-common-actions`, `artcraft-services`; full read of `docs/mcp.md`,
`docs/control-protocol.md`, `docs/agents.md`, the MCP crate sources, and the CLI `main.rs` of
each app.

---

## 1. The org at a glance

`storytold` is not just the 12 Craft apps. Relevant repos:

| Repo | Role | Relevance |
|---|---|---|
| `photocraft`, `vectorcraft`, `filmcraft`, `lightcraft`, `pdfcraft`, `effectcraft`, `designcraft`, `wordcraft`, `deckcraft`, `gridcraft`, `cadcraft`, `soundcraft` | The 12 Craft apps | **All have MCP + control channel + CLI** |
| `craft-libs` | Shared Rust libs (`crates/ui` = egui theme/docking/tabs/icons) | UI consistency; no MCP |
| `craft-common-actions` | CI/CD GitHub Actions (release pipelines) | **Not relevant** despite the name — it is release automation, not agent automation |
| `craft-launcher` | The desktop app launcher | **No programmatic interface** (see §6) |
| `artcraft-services` | The hosted cloud API + frontends | **A separate REST integration surface** (see `03-ARTCRAFT-CLOUD-API.md`) |
| `artcraft`, `artcraftx`, `placeholder-artcraft` | ArtCraft product / 3D engine | Different product line |
| `craft-fonts`, `craft-repo-status-app`, `photocraft-corpus` | Fonts, CI status dashboard, test data | Not relevant |

---

## 2. The universal architecture

Every app is a **Rust workspace** with this shape:

```text
<repo>/
├── crates/
│   ├── engine/          # the command registry + document model  ← the capability core
│   ├── ui-egui/         # the GUI (egui)
│   ├── mcp/  OR automation/   # the MCP server      ← varies by family
│   ├── <format>/...     # codec crates (psd, svg, docx, xlsx, …)
│   └── …
├── apps/
│   ├── <app>/           # the desktop binary  (supports --control PORT)
│   ├── <app>-cli/       # the CLI binary       (supports `mcp` subcommand)
│   └── <app>-web/       # WASM build
├── docs/
│   ├── mcp.md
│   ├── control-protocol.md
│   └── …
└── .mcp.json            # shipped by effectcraft + filmcraft only
```

### 2.1 The command registry — why "every functionality" is already covered

This is the single most important design fact.

> From `effectcraft/docs/agents.md`:
> *"Everything in EffectCraft is an engine command with a stable id and JSON params. Menus,
> shortcuts, panel gestures, the CLI, the control channel and MCP all go through the same
> commands, so anything a user can do, an agent can do too."*

The same statement holds, in the same words, for the other apps. The registry lives in
`crates/engine/src/cmd*` and exposes, per command: `id`, label, menu path, keyboard shortcut,
parameter documentation, and current enabled state.

Consequences for your design:

1. **You do not need a tool per Photoshop feature.** `command_list` + `run_command {id, params}`
   is a complete, universal escape hatch. The curated tools (`draw_shape`, `set_cell`,
   `add_slide`) are ergonomics.
2. **Tool schemas are discoverable at runtime**, so a gateway does not need to hard-code
   anything. It can proxy `tools/list` through.
3. **Command ids are stable** — they are the same strings the CLI uses, the same strings the
   control protocol uses, the same strings the UI uses.

Measured command-id density (approximate count of dotted command-id strings under
`crates/engine/src`; an upper bound, not a precise registry count):

| App | ~command ids | engine src files |
|---|---|---|
| filmcraft | 1,122 | 104 |
| photocraft | 1,053 | 160 |
| vectorcraft | 1,006 | 149 |
| effectcraft | 892 | 85 |
| wordcraft | 735 | 14 |
| lightcraft | 579 | 77 |
| designcraft | 531 | 13 |
| gridcraft | 370 | 15 |
| pdfcraft | 252 | 17 |
| deckcraft | 233 | 10 |
| soundcraft | 151 | 10 |
| cadcraft | 134 | 23 |

### 2.2 Three interchangeable transports

All three go through the same registry:

```text
                      ┌──────────────────────────────────────┐
   <app>-cli mcp ─────┤                                      │
   (stdio MCP)        │   engine command registry            │
                      │   (crates/engine/src/cmd*)           │
   <app> --control ───┤      stable id + JSON params         │
   (loopback TCP)     │                                      │
                      │                                      │
   <app>-cli run ─────┤                                      │
   (batch CLI)        └──────────────────────────────────────┘
```

Three more capabilities exist that only the GUI transport gives you: synthetic UI input
(`ui.pointer`, `ui.click`, `ui.key`, `ui.type`), dialog driving (`ui.dialog.open/set/confirm`),
and screenshots of the real window.

---

## 3. Family A — `crates/automation`

**Apps:** photocraft, filmcraft, effectcraft, pdfcraft, soundcraft

### 3.1 PhotoCraft (most complete reference implementation)

**Crate:** `crates/automation` — `photocraft-automation`
**MCP implementation:** official Rust SDK `rmcp` with `#[tool]` / `#[tool_router]` macros,
Tokio async, `crates/automation/src/server.rs` (987 lines)

**Tool annotations** are applied centrally in `src/server/conventions.rs`:
read-only tools are `command_list`, `doc_inspect`, `session_list`, `render_preview`,
`doc_render_preview`, `ui_inspect`, `ui_screenshot`; additive tools are `doc_new`, `doc_open`;
everything else is marked destructive + not idempotent. Every schema gets
`additionalProperties: false` and unknown arguments are rejected with JSON-RPC `-32602`
*before* execution.

**MCP tools (21):**

| Tool | Purpose |
|---|---|
| `command_list {filter?, enabled_only?}` | Discover engine command ids, params docs, enabled state |
| `command_run {id, params?, wait?}` | Run one engine command |
| `command_batch {steps[], stop_on_error?, atomic?, label?}` | Run several; `$N.path` references into earlier results |
| `command_run` + `file.export.renderVideo` | Special-cased: emits MCP progress notifications when `_meta.progressToken` is set; cancellable via `notifications/cancelled` |
| `doc_new`, `doc_open {path}`, `doc_save {path?, tgaBits?}`, `doc_export`, `doc_close {index?}`, `doc_select {index}` | Document lifecycle |
| `doc_inspect {index?}` | Layer tree, history, selection, channels |
| `render_preview {max_side?, index?}`, `doc_render_preview {max_side?}` | PNG back as MCP image content |
| `jobs_list`, `jobs_cancel {job?}` | Background jobs (filters, content-aware fill, photomerge, `.abr` import) |
| `session_list` | Open documents + active index |
| `ui_inspect`, `ui_screenshot`, `ui_pointer`, `ui_menu_invoke {id}`, `ui_set {fields}` | **Bridge mode only** — drive the live window |
| `control_call {method, params}` | **Bridge mode only** — raw passthrough to any control-protocol method |

**Resources:** `photocraft://document` (live `doc_inspect` JSON) and `photocraft://commands`
(live `command_list` JSON). List/read are uncached; catalogs are private + cached 10 min. The
2026-07-28 `resultType` / `ttlMs` / `cacheScope` fields are emitted.

**Modes:**
```sh
# Headless: in-process engine Session, no window, no GPU
photocraft-cli mcp --automation-read-root /work --automation-write-root /work

# Bridge: forward every tool over the loopback control channel to a live app
photocraft-cli mcp --bridge 127.0.0.1:7878 --control-token-file /path/token
```

**Extra transport (unique to PhotoCraft):** `photocraft-cli serve` — a *non-MCP* JSON-lines
server on stdio or TCP (`--port`) implementing `engine.execute`, `jobs.list/cancel`,
`engine.commands`, `session.list`, `doc.open/new/save/inspect/render/select/close`, `batch`,
`methods`. It is explicitly documented as *"the fastest way for a script or agent to make many
edits: no MCP framing, no app start-up per command."* Implementation: `crates/automation/src/rpc.rs`.

### 3.2 FilmCraft

**Crate:** `crates/automation` — also `rmcp`, `src/server.rs` (1001 lines), plus
`src/long_job.rs` for progress + cancellation.
**Docs:** `docs/agents.md` (two parts: driving FilmCraft, developing FilmCraft as an agent) —
the most complete narrative documentation in the org.

**Tools (16):** `command_list`, `command_run`, `command_batch`, `doc_inspect`,
`project_inspect`, `sequence_inspect`, `render_preview`, `render_frame`,
`media_import {…}` (playlist import), `ui_inspect`, `ui_click`, `ui_drag`, `ui_key`, `ui_type`,
`ui_screenshot`, `ui_control`.

**Modes:** `filmcraft-cli mcp --demo` / `--project p.fcproj` (headless),
`--bridge 127.0.0.1:9876` (live), `--data-dir DIR` (presets).

> **Security note from the docs:** *"there are no folder-confinement flags such as
> `--automation-read-root`, so the server can read and write wherever the user can."*
> FilmCraft headless is **not** sandboxed. See `04-SECURITY.md`.

### 3.3 EffectCraft

**Crate:** `crates/automation` — hand-written JSON-RPC (`src/server.rs`, `src/tools.rs` 1008
lines, `src/bridge.rs`, `src/confine.rs`, `src/long_job.rs`, `src/autosave.rs`).
**Also has:** `crates/script` — a full **ExtendScript / Adobe After Effects expression engine**
(`lib.rs`, `runtime.rs`, `ui.rs`, `scriptui.rs`, `socket.rs`, `prelude.js`, `matchnames.rs`).
That means `run_script` lets an agent run real AE-style JavaScript against the engine.

**Tools (~34):** `list_commands`, `execute_command`, `describe_command`, `list_effects`,
`list_fonts`, `add_effect`, `effects_group`, `get_state`, `run_script`, `get_project`, `get_comp`,
`flatten`, `get_layer`, `get_property`, `set_property`, `add_keyframe`, `render_frame`,
`open_project`, `save_project`, `history`, `undo`, `redo`, `batch`, `control`, `screenshot`,
`ui_inspect`, `ui_elements`, `ui_click`, `ui_drag`, `ui_key`, `ui_type`, `ui_set`.

**Modes:** `effectcraft-cli mcp` (headless, `--demo`/`--project`/`--gpu`/`--autosave`),
`effectcraft-cli mcp --bridge 9877` (live).

### 3.4 PdfCraft

**Crate:** `crates/automation` with `src/mcp.rs` (543 lines) + `src/tools.rs` (the largest, most
task-oriented tool set in the org), plus domain modules `a11y.rs`, `comments.rs`, `content.rs`,
`forms.rs`, `links.rs`, `measure.rs`, `printing.rs`, `redact.rs`, `signing.rs`.

**This is the one app that is task-oriented rather than command-oriented.** Its tool table is
PDF verbs, not generic commands: `doc_open`, `doc_list`, `doc_info`, `doc_close`, `doc_save`,
`doc_set_info`, `page_render`, `page.rotate`, `a11y.check`, `a11y.report`, `a11y.alt_text`,
`comment.*`, `form.*`, `link.*`, `measure.*`, `redact.*`, `sign.*`, `print.*`, `actions.wizard`.
It also has a `tool_for_command(id) -> Option<&str>` mapping table that exposes **each engine
command as a first-class MCP tool** (`src/tools.rs:1152`).

**Distinct features:**
- `--root DIR` — confines **all** reads and writes, including commands run through the common
  tools. May be supplied at most once. Fails closed.
- `--compact` — exposes a reduced 5-tool surface (`command_list`, `command_run`,
  `command_batch`, `doc_inspect`, `render_preview`) plus `tool_search` / `tool_call`.
  **This is exactly the context-management pattern your gateway should copy.**
- `pdfcraft-cli ui --control FILE <method>` — **PdfCraft's control channel is a file, not a
  port.** The app writes a small JSON control file (with owner/mode validation, <100 KiB) that
  the CLI reads. `pdfcraft-cli run --script steps.json` runs a JSON array of
  `{"tool": ..., "args": {...}}` — a ready-made batch-script format.

### 3.5 SoundCraft

**Crate:** `crates/automation` with `src/mcp.rs` (251 lines) — the **smallest, cleanest** MCP
implementation in the org and a good reference for a minimal implementation.

**Tools (17):** `list_commands {filter?}`, `execute {command, params}`,
`batch {calls[], keep_going?}`, `inspect_session {detail: summary|full}`,
`new_session {name?, sample_rate?, template?}`, `open_session {path}`, `save_session {path}`,
`import_audio {path, track?, at?}` (WAV/AIFF/FLAC/MP3/OGG/AAC/M4A/ALAC/CAF),
`bounce_mix {path, format: wav|aiff|flc, bit_depth?, start?, end?, normalize?}` (returns peak
dBFS + integrated LUFS), `parity`, `screenshot`, `ui_inspect`, `ui_set {state}`,
`menu_invoke {path}`, `click {x,y,button?,count?}`, `drag {x,y,to_x,to_y}`,
`key {key,cmd?,shift?,alt?,ctrl?}`.

`APP_ONLY.` prefixed tools (screenshot, ui_*, menu_invoke, click, drag, key) require the bridge.
**Modes:** `soundcraft-cli mcp [--demo | --in file]`, `--connect 7801`.

---

## 4. Family B — `crates/mcp`

**Apps:** vectorcraft, lightcraft, designcraft, gridcraft, cadcraft, deckcraft, wordcraft

**Shared implementation** (see `vectorcraft/crates/mcp/src/lib.rs`, the fullest example):

```rust
//! [Model Context Protocol](https://modelcontextprotocol.io) over stdio: newline-delimited
//! JSON-RPC 2.0, hand-written (no async runtime). […] forwards everything to a `Backend`:
//! - `Remote` talks to a running desktop app through its loopback JSON-lines control channel
//!   (`vectorcraft --control 7979`): one {"id","method","params"} line in, one
//!   {"id","ok","result"|"error"} line out.
//! - `Headless` hosts an in-process `vectorcraft_engine::Session` and implements the same
//!   control-channel method names itself (rendering screenshots with `vectorcraft-render`),
//!   so agents can draw and look at the result without a window.
```

Module layout, identical across all 7 apps:
`server.rs` (framing + lifecycle + tools/resources/prompts), `backend.rs` (the `Backend` trait
+ `Remote`), `headless.rs`, `tools.rs`, plus optional `resources.rs`, `prompts.rs`, `logging.rs`,
`progress.rs`, `base64.rs`.

**Protocol version negotiation** (`vectorcraft/crates/mcp/src/server.rs:9-12`):
```rust
pub const PROTOCOL_VERSION: &str = "2025-06-18";
const MODERN_VERSION: &str = "2026-07-28";
const SUPPORTED_VERSIONS: &[&str] = &[MODERN_VERSION, PROTOCOL_VERSION, "2025-03-26", "2024-11-05"];
```
The server tracks whether the client is "modern" (2026-07-28) and, if so, adds
`resultType`/`ttlMs`/`cacheScope` to `tools/list`, `resources/list`, `resources/templates/list`
and `prompts/list` (TTL 600 000 ms, `cacheScope: "private"`) and to `resources/read`/`prompts/get`
(TTL 0). `handle_line` is public so a caller can drive the server message-by-message.

**Robustness features** (worth copying in any wrapper):
- `engine::guard::catch_panic` wraps every request — a panic becomes an `INTERNAL_ERROR` reply
  and the server keeps serving.
- Legacy JSON-RPC batch arrays are still answered correctly.
- Logging is a process-wide queue; only a client that sent `logging/setLevel` receives
  `notifications/message` records, and they are emitted **after** the reply to the line that
  produced them.
- Logs go to stderr only; stdout carries protocol messages exclusively.

### 4.1 VectorCraft — the most fully-featured Family-B server

**Tools (32):** `command_list`, `command_run`, `command_batch`, `inspect_document`,
`inspect_ui`, `run_command`, `list_commands`, `doc_inspect`, `render_preview`, `screenshot`,
`ui_inspect`, `ui_screenshot`, `open_file`, `save_file`, `export`, `undo`, `redo`, `draw_shape`,
`draw_path`, `create_graph`, `transform`, `apply_effect`, `set_paint`, `pathfinder`,
`pointer_gesture`, `press_key`, `type_text`, `add_text`, `text_wrap`, `select_tool`,
`invoke_menu`, `open_panel`.

**Also the only Family-B app with MCP prompts and resources:**
- `resources.rs`: `vectorcraft://document`, `vectorcraft://object/{id}`,
  `vectorcraft://command/{id}`, `vectorcraft://effect/{id}`, `vectorcraft://swatch/{name}`,
  plus `TEMPLATES` and `DOC_JSON_URI` resource templates — i.e. read one object at a time rather
  than dumping the whole document.
- `prompts.rs` (564 lines): `PROMPTS` with `PromptArg` / `PromptDef` — ready-made workflows.
- `INSTRUCTIONS` string in `server.rs:22` tells the agent exactly how to work: *"Draw with
  draw_shape / draw_path, change colours with set_paint, look with render_preview and
  doc_inspect. Every menu action is a command: find it with command_list and run it with
  command_run (or command_batch for several)."*

`docs/mcp.md` is **3,154 lines** — the most extensive protocol documentation in the org.

**Modes:** `vectorcraft-cli mcp --connect 127.0.0.1:7979` (remote),
`vectorcraft-cli mcp --headless`, `vectorcraft-cli mcp --in file.vc9 --automation-read-root R
--automation-write-root W`. With no flag: try `127.0.0.1:7979`, fall back to headless.

### 4.2 LightCraft

**Tools (28):** `command_list`, `command_run`, `command_batch`, `run_command`,
`list_commands`, `doc_inspect`, `inspect_ui`, `list_controls`, `list_widgets`, `render_preview`,
`render_photo`, `screenshot`, `ui_inspect`, `ui_screenshot`, `query_photos`, `select_photos`,
`crop`, `set_develop`, `get_develop`, `apply_preset`, `import`, `export`, `clipboard`, `click`,
`type_text`, `press_key`, `pointer_gesture`, `set_ui`.

Notable: `list_widgets` / `list_controls` expose the egui widget tree — a generic way to find and
drive any control. LightCraft is the only Family-B app with `progress.rs` and `base64.rs`
modules (long-running raw development needs progress + inline images).

**Modes:** `lightcraft-cli mcp [--connect 127.0.0.1:7980 | --headless] [--demo | --library]
[--compact]`.

### 4.3 DesignCraft

**Tools (25):** `execute`, `batch`, `list_commands`, `menu_list`, `new_document`,
`open_document`, `save_document`, `export_png`, `get_story`, `set_story_text`, `inspect_document`,
`render_page`, `place_image`, `select_tool`, `ui_set`, `ui_inspect`, `pointer`, `click`, `drag`,
`key`, `type_text`, `dialog_set`, `dialog_confirm`, `dialog_cancel`.

Notable: the `dialog_*` trio gives explicit dialog field control. DesignCraft also has a
**script format** (`designcraft-cli script`, `.dcs` files) with `"$N.path"` result references and
`"${N.path}"` string interpolation — same convention as PhotoCraft's `command_batch`.

**Modes:** `designcraft-cli mcp` (headless), `--connect 7979`, `--in file.dcd`, `--sample`.

### 4.4 GridCraft

**Tools (21):** `new_workbook`, `open_workbook`, `save_workbook`, `inspect_workbook`, `read_range`,
`write_range`, `get_cell`, `set_cell`, `format_range`, `sort_range`, `filter`, `evaluate_formula`,
`insert_chart`, `create_table`, `select`, `list_commands`, `list_functions`, `execute_command`,
`undo`, `redo`, `screenshot`.

Notable: `list_functions` exposes the **spreadsheet formula function catalogue** — the
spreadsheet equivalent of `command_list`.

**Modes:** `gridcraft-cli mcp [--connect 7979 | --in book.xlsx | --sample budget]`.
Docs: 87 lines, the cleanest short reference in the org.

### 4.5 CADCraft — smallest and most specialised

**Tools (15):** `command_line {text}`, `execute`, `list_commands`, `new_drawing`, `open`,
`save`, `script`, `inspect_drawing`, `query_entities`, `render`, `screenshot`, `ui_click`,
`ui_inspect`, `cancel`.

The standout is **`command_line {text}`** — CADCraft exposes a natural-language-shaped tool that
types at the AutoCAD-style command line exactly like a person:
`command_line {"text": "line 0,0 @10,0 @0,5 c"}` → draws and closes the polyline;
`"circle 5,2 1"`; `"offset 0.5"`; `"zoom e"`. Spaces act as Enter. It returns the new prompt,
keywords and output. **This is the single best example in the org of designing for LLM ergonomics
rather than exposing a raw RPC.**

Fail-closed behaviour: *"Without `--connect` (or with an unknown argument) `cadcraft-cli mcp`
exits with an error instead of falling back to a headless session, so a client meant for the app
never edits a separate drawing by mistake."* Adopt this default.

### 4.6 DeckCraft

**Tools (25):** `new_presentation`, `open_presentation`, `save_presentation`, `export`,
`inspect_document`, `inspect_slide`, `render_slide`, `add_slide`, `go_to_slide`, `add_shape`,
`add_text_box`, `set_text`, `insert_picture`, `insert_table`, `insert_chart`, `select`,
`select_tool`, `pointer`, `key`, `type_text`, `list_commands`, `run_command`, `batch`,
`screenshot`, `call_app`.

Notable: **`call_app`** — DeckCraft can call *another* Craft app. This is the one cross-app
primitive that already exists upstream. Investigate it first; it may be the seed of a
cross-app gateway. Also `docs/animation-parity.md`, `docs/slideshow-parity.md`.

### 4.7 WordCraft

**Tools (15):** `new_document`, `open_document`, `save_document`, `inspect_document`, `get_text`,
`select_text`, `type_text`, `execute`, `batch`, `list_commands`, `key`, `click`, `ui_inspect`,
`render_page`, `screenshot`, `parity`.

Notable: **`--author "Claude (copyedit)"`** — headless MCP takes an author name, and
`file.setAuthor {"name": ...}` sets it at runtime. Tracked changes and comments are recorded
under that name, so an agent's edits are attributable in review. The docs explicitly recommend
naming the agent. **Adopt this convention in your gateway for every app that supports it.**
Also: `review.trackChanges {"value": true}` — note the explicit `value`, because omitting it
*enables* tracking via toggle, which turns it **off** in a saved document.

Bridge auth differs here: it sends a **control key** read from `WORDCRAFT_CONTROL_KEY` or from
the key file the app writes at start, and only to loopback addresses.

---

## 5. Control protocol (the de-facto "REST API")

Present in all 12 apps. PhotoCraft's `docs/control-protocol.md` is the most complete (349+ lines
of methods); the other 11 mirror it closely.

### 5.1 Transport

| App | Transport | Example |
|---|---|---|
| photocraft | TCP + bearer token | `photocraft --control 7878 --control-token-file /path/token` |
| filmcraft | TCP | `filmcraft --control 9876` |
| effectcraft | TCP | `effectcraft --control 9877` |
| vectorcraft | TCP | `vectorcraft --control 7979` |
| lightcraft | TCP | `lightcraft --control 7980` |
| designcraft | TCP | `designcraft --control 7979` |
| gridcraft | TCP | `gridcraft --control 7979` |
| cadcraft | TCP | `cadcraft --control 7979` |
| deckcraft | TCP | `deckcraft --control 7990` |
| soundcraft | TCP | `soundcraft --control 7801` |
| wordcraft | TCP + **control key** | `wordcraft --control 7981` |
| pdfcraft | **control file** (JSON) | `pdfcraft --control ~/.pdfcraft-control.json` |

Loopback only. Defaults cluster on 7979–7981 with two outliers (filmcraft 9876, effectcraft 9877).

### 5.2 Wire format (identical across apps)

Auth frame first, on every connection:
```json
{"id": "auth", "method": "auth", "params": {"token": "<64 hex chars>"}}
```
Then one request per line:
```json
{"id": 1, "method": "ui.inspect", "params": {}}
```
One reply per line, same `id`:
```json
{"id": 1, "ok": true,  "result": { ... }}
{"id": 2, "ok": false, "error": "unknown tool `foo`"}
```
PhotoCraft's token is 256-bit, generated at launch, `0600` on Unix, delivered via
`--control-token-file` (never on the command line), with `PHOTOCRAFT_CONTROL_TOKEN` /
`PHOTOCRAFT_CONTROL_TOKEN_FILE` env equivalents. If neither is configured it generates one and
writes it to stderr.

### 5.3 The method vocabulary

Near-identical across apps — this *is* the shared REST-ish surface:

| Method | Effect |
|---|---|
| `engine.execute {command, params, wait?}` | **Any** engine command by id. This is the universal endpoint. |
| `engine.commands {filter?}` | Command registry with labels, menu paths, shortcuts, param docs, enablement |
| `ui.inspect` | Full UI state: tool, panels, dock, views, dialogs, windows, `toolOptions`, GPU info, running jobs, notices |
| `ui.set {…}` | Change UI state: tool, panels, dock, zoom, center, fit, theme, brush size/section/tab, gradients, shape stroke, eyedropper options, crop overlay/shield, dock geometry |
| `ui.menu.invoke {id, params?, wait?}` | Activate a menu item like a click; opens its dialog when no params given |
| `ui.menu.list` | The menu tree |
| `ui.pointer {events[], tool?, modifiers?, button?}` | **Document-coordinate** synthetic pointer with `pressure`, `tiltX/tiltY`, `rotation` — a simulated pen. Ctrl/Cmd/Alt/Shift/Space modifiers. `command: true` turns the gesture into a Move-tool drag. |
| `ui.click {x,y,button?,count?}` / `ui.move {x,y}` | Screen-point synthetic input |
| `ui.key {key, command?, shift?, alt?, ctrl?}` | Press+release |
| `ui.type {text}` | Type into the focused widget |
| `ui.dialog.open {kind, fields?}` / `ui.dialog.set {dialog,field,value}` / `ui.dialog.confirm` / `ui.dialog.cancel` | Full dialog driving: `newDocument`, `about`, `layerStyle`, `colorPicker`, `command`, crop presets, `shell` (workspace/pixel-aspect dialogs), Preferences (partially refused) |
| `ui.window.open/close`, `ui.resize`, `ui.focus` | Window management |
| `ui.screenshot {path?, focus?}` | PNG; base64 in the reply, or written under the automation write root. Raises the window first because occluded macOS windows stop rendering. |
| `ui.gpu.simulateLoss` | Act as if the wgpu device was lost — testing the CPU fallback |
| `app.open {path}` / `app.save {path?, tgaBits?}` / `app.quit` | Capability-scoped file I/O through the automation roots |
| `jobs.list` / `jobs.cancel {job?}` | Background jobs with `state` (running/done/failed/cancelled), `progress` 0–1, result or error |

### 5.4 Transport limits (PhotoCraft, likely shared)

- 1 MiB max encoded request line
- 8 MiB max encoded JSON reply
- 16 simultaneous connections per listener
- 30 s socket read/write timeout
- 256 steps max in `batch` / `command_batch`
- desktop waits up to 60 s for a reply; bridge client times out at 55 s (strictly lower, so the
  bridge's error is what you see)

### 5.5 Documented operational gotchas (copy these into your gateway's error handling)

- **Wayland frame-callback starvation.** On Wayland the control drain only runs on compositor
  frame callbacks, so an asleep/occluded window makes every request time out while the app is
  healthy. The error message says so.
- **Bridge edits are never auto-retried.** A transport failure mid-request reports that the
  operation *may have completed* — inspect the document before retrying. Only pure-read tools
  (`ui_inspect`, `doc_inspect`, `command_list`, `jobs_list`, `session_list`, `ui_screenshot`) get
  one automatic retry.
- **Idle connections close after 30 s**; the bridge proactively reconnects before a call if idle.
- **Background jobs.** Long commands (all `filter.*`, content-aware fill/scale, photomerge,
  `.abr` import, file opens, interactive saves) run as jobs. Pass `"wait": false` → `{job,
  pending: true}`, then poll `jobs.list`. While a job runs, commands that would edit its document
  fail with "… is still running on this document".

---

## 6. Craft Launcher — **no** programmatic interface

Worth knowing because it is the obvious place to look for a cross-app entry point. It isn't one.

`craft-launcher` lists the 12 apps (compiled-in `SUITE: [CraftApp; 12]` in
`crates/core/src/catalog.rs:99`), detects installs, downloads from GitHub releases or the feed at
`https://api.storyteller.ai/v1/craft_apps/release_info`, installs them, and launches them.

**It cannot be scripted.** Verified absence of:

- No CLI subcommands. The entire argument surface is `--version` / `-V` and `--hidden`.
  No `clap` or any arg parser dependency in the repo.
- No JSON/stdout protocol. The only `println!` is the version line.
- No HTTP/websocket server, no unix socket, no named pipe, no file-based command queue.
- **It cannot launch an app with arguments.** `install::launch()` calls
  `process::launch_binary(path, &[])` — the args slice is hard-coded empty.
- The single network listener is a fixed **127.0.0.1:47413** single-instance arbitration socket
  that can only do `artcraft-launcher:show` or quit the launcher. Its own docs say: *"The worst
  another local program can do with any of this is bring the window forward or make the launcher
  quit."*

`docs/` contains only brand assets and screenshots — no markdown at all. No MCP anywhere.

**Implication:** you launch the app binaries yourself, not through the launcher. The launcher is
useful only for install/update/version discovery.

---

## 7. Cross-app primitive: `call_app`

`deckcraft` exposes a `call_app` MCP tool. This is the only existing cross-app call surface in
the org and should be the first thing you investigate — it may already encode the invocation
contract you would otherwise design.

---

## 8. Documentation map (what to read in each repo)

| Path | Contents |
|---|---|
| `<repo>/docs/mcp.md` | MCP server reference. Range: 37 lines (deckcraft) → 3,154 lines (vectorcraft). |
| `<repo>/docs/control-protocol.md` | Control channel methods. Present in 11 apps; **pdfcraft has none** (file-based instead). |
| `<repo>/docs/agents.md` | filmcraft, effectcraft, designcraft (narrative agent docs) |
| `<repo>/docs/architecture.md` | Crate layering, command engine |
| `<repo>/crates/mcp/src/lib.rs` or `crates/automation/src/lib.rs` | The module doc-comment is an accurate architecture summary |
| `photocraft/book/src/architecture/automation.md` | **The clearest cross-transport diagram in the org** |
| `photocraft/book/src/automation/security-model.md` | Automation security model |
| `photocraft/book/src/security/automation-security.md` | Security posture |
| `effectcraft/docs/scripting-parity.md` | Extent of ExtendScript/AE-expression parity |
| `<repo>/docs/plugins.md` | photocraft, vectorcraft, effectcraft — plugin/extension points |
| `<repo>/.mcp.json` | Shipped by **effectcraft** and **filmcraft** only |

---

## 9. Engineering conventions worth respecting

From `craft-libs/AGENTS.md` and the shared `craftrules` standards, enforced workspace-wide:

- `#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented,
  clippy::todo, clippy::unreachable)]` at the top of every `lib.rs`
- `unsafe_code = "forbid"` — **no unsafe anywhere in any Craft app**
- Public API compatibility is a hard rule: existing contracts, defaults, limits and pagination
  must not change; new behaviour goes behind a new path (`…/list_v2/…`), reserving `/v2`.
- Every crate's `mod.rs` holds declarations only.
- `cargo fmt --check`, `cargo clippy --workspace --all-targets -- -D warnings`,
  `cargo test --workspace` before merge.

Your gateway is not a Craft app, but if you want upstream contributions, match these.