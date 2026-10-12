# 08 — Required Tools: What the Gateway Must Add

The specification. Every tool below is either **not implemented by any app** or **must be
composed by the gateway** to satisfy the perception, verification and team requirements in
`06-PERCEPTION.md` and `07-SCAICO-TEAMS.md`.

---

## Design constraints

**1. Flat namespace, app-namespaced payload.** Tools are `craft_*`; apps are a parameter.

```rust
craft_run_tool(app: "photocraft", tool: "doc_render_preview", args: {...})
```

**2. Allowlist-first.** Every token carries an allowlist; the server enforces it. This is what
makes the 12-app surface addressable in a team context (`07-SCAICO-TEAMS.md`).

**3. Low default cost.** Structure before pixels. `craft_look` defaults to the cheapest render
that answers the question.

**4. Every claim traceable.** `craft_record` requires an evidence id (a render, a revision, an
assert). This mechanically enforces the "no speculative claims" rule your TimeAttack team already
states in prose.

---

## A. Perception — what the apps cannot do

### A1. `craft_look` — unified render ⭐

```rust
craft_look {
    app: App,
    scope:  "content" | "window" | "region" | "outline" | "contact_sheet",
    index:  Option<u32>,        // document / page / slide / artboard / frame
    region: Option<Rect>,       // document coords — the missing capability
    max_side: Option<u32>,      // default 1024, clamp 16..4096
    detail: "thumbnail" | "normal" | "full",
    layer:  Option<String>,     // render one layer in isolation
    path:   Option<String>,     // also write to disk
}
```

Maps to `render_preview` / `doc_render_preview` / `render_page` / `render_slide` / `render_frame`
/ `render_photo` / `render` / `ui.render` depending on app and scope. Returns MCP image content
plus a metadata block:

```json
{
  "content": [{ "type": "image", "data": "…", "mimeType": "image/png" }],
  "meta": { "app":"photocraft","revision":42,"width":1024,"height":576,
            "content_hash":"sha256:ab12…","cost_tokens":1150,
            "source":"headless:doc_render_preview" }
}
```

The `content_hash` is what enables caching and diffing. **Always return it.**

**Why one tool instead of twelve:** the agent should not have to know that PdfCraft says
`render_preview` and DeckCraft says `render_slide`.

### A2. `craft_diff` — the biggest missing capability ⭐⭐

Nothing in any app computes "what changed". This is the highest-value addition.

```rust
craft_diff { app: App, from: Revision, to: Revision, max_side: u32 }
```

Returns **both**:
- a **structural diff** as JSON — layers added/removed/reordered/props-changed, selection, history
- a **visual diff** as an image — per-pixel delta, optionally with unchanged regions dimmed

Derive `Revision` from `doc_inspect` (PhotoCraft already reports one). If the app doesn't, hash the
structural JSON.

This directly replaces the agent pattern "render again and stare at both" — which costs two
full renders and a lot of luck.

### A3. `craft_contact_sheet` — N pages in one image ⭐

```rust
craft_contact_sheet { app: App, indices: Vec<u32>, cols: u32, cell: u32, labels: bool }
```

Reviewing a 30-slide deck currently costs 30 tool calls and 30 images (~900 k tokens). One
contact sheet costs one call and ~2 k tokens. **Same for PDF pages, film sequence frames,
LightCraft photo grids, VectorCraft artboards.**

This is the single biggest token saving in the whole design.

### A4. `craft_lod` — look closer without re-rendering everything

```rust
craft_lod { app: App, index: u32, region: Rect, levels: u32 }
```

Renders a zoom pyramid (or tile set) so the agent can escalate from thumbnail → region → full
resolution on demand. No app has this.

### A5. `craft_probe` — the inverse of a render ⭐

```rust
craft_probe { app: App, x: f64, y: f64 }   // document coordinates
→ { "layer_id": "…", "object_id": "…", "type": "Group", "depth": 3,
    "bounds": [...], "pixel": {"r":214,"g":88,"b":40,"a":255},
    "text_at_point": "Northwind", "cmd_at_point": "Eyedropper" }
```

*"What is at this pixel?"* For PhotoCraft this is the layer under the cursor plus the composited
colour. CADCraft has a spatial half of this already (`query_entities {window: [[x0,y0],[x1,y1]]}`)
— **generalize it to all apps.**

`ui.inspect` already reports `layerMenu` and `canvasToolMenu`; this is the document-space
equivalent.

### A6. `craft_read_resource` — templated resources as a tool

```rust
craft_read_resource { app: App, uri: String }   // "vectorcraft://object/{id}" with {id} bound
craft_resource_templates { app: App }
```

Ten of twelve apps expose URI templates (`object/{id}`, `doc/{doc}/page/{page}/image{?dpi}`,
`photo/active`, …). A flat tool list cannot express a template. **Expose them as a tool so the
agent can address one object or one low-DPI page instead of dumping the document.**

### A7. `craft_play` — audio perception (SoundCraft's missing tier)

```rust
craft_play { app: App, target: "waveform" | "spectrogram" | "stems" | "meter", from, to }
→ image content (spectrogram is an image!) + numeric metrics
```

SoundCraft can only return peak dBFS and integrated LUFS — measurements, not perception.
A spectrogram **is** an image, so an image-capable agent can read it. **This is the cheapest way to
give an agent audio perception.** Requires a renderer the app doesn't have; note it as upstream
work.

---

## B. State and status

### B1. `craft_status` — one call, all apps ⭐

```rust
craft_status { app?: App }   // omitted = every app
→ { "apps": [
      { "app":"photocraft", "available":true, "running":"headless",
        "documents":[{"index":0,"path":"logo.psd","dirty":true,"revision":42}],
        "jobs":[], "mode":"headless", "roots":{"read":"/work","write":"/work"},
        "last_error":null, "render_hash":"sha256:ab12…" } ] }
```

The coordinator's `get_zone_detail`. Without it, an agent has to probe 12 apps to learn what
exists. **Also serves health monitoring** — if an app's process died, say so here.

### B2. `craft_revision` + `craft_wait` — polling, encapsulated ⭐

No app implements `resources/subscribe`. So the gateway provides it:

```rust
craft_wait { app: App, until: "revision_change" | "job_done" | "idle", timeout_ms: u32 }
```

Blocks (server-side) until the document revision changes or a background job completes, then
returns the new state. **Turns the missing push protocol into a pull-with-a-long-timeout**, which
every client already supports.

### B3. `craft_history`

```rust
craft_history { app: App, limit: u32 }   → undo stack with labels
```

Combined with `craft_undo`/`craft_redo`, this is how an agent explores safely: snapshot the state,
try something, look, diff, undo if wrong.

---

## C. Verification and safety

### C1. `craft_snapshot` / `craft_restore` ⭐⭐

```rust
craft_snapshot { app: App, label?: String } → { "token": "snap_…", "revision": 42 }
craft_restore { app: App, token: String }    → { "restored_to": 42 }
```

Copies the document into the session asset store; restores by re-opening. PhotoCraft already has
`command_batch {atomic: true}` and a full undo stack — but a *file-level* checkpoint survives
process death. **This is the agent's seatbelt and the cheapest insurance in the design.**

Auto-snapshot policy: before any batch with >1 destructive step, and before any `app.save`.

### C2. `craft_assert` — declarative postconditions ⭐⭐

```rust
craft_assert { app: App, expect: Assertion }
// structural (default, deterministic):
{ "layer_exists": "Northwind" }
{ "doc_size": [2000, 1500] }
{ "export_format": "png", "output_path": "logo.png" }
{ "selection_count": 3 }
{ "history_top": "filter.blur.gaussianBlur" }
{ "all": [ … ] }
// visual (opt-in, tolerance required):
{ "mean_luma_delta_from": { "revision": 41 }, "within": 0.02 }
{ "region_non_empty": { "rect": [0,0,100,100] } }
```

Returns pass/fail with the observed value.

**This is the mechanical form of your TimeAttack rule.** An agent that must pass
`craft_assert` before `craft_record` can prove its work cannot narrate a success it did not
achieve.

**Default to structural assertions.** Pixel assertions will flake across renderers, fonts and
colour-management configurations. Only assert on pixels when the user has accepted that.

### C3. `craft_run` — guarded execution

```rust
craft_run {
    app: App,
    command: String,
    params: Value,
    require?: Vec<Assertion>,   // must pass BEFORE running
    expect?: Vec<Assertion>,    // must pass AFTER
    snapshot?: bool,            // default true if destructive
}
```

Declarative guard rails. A coordinator can grant an agent the ability to run commands but require
"document size must be 2000×1500 afterwards" — policy expressed as data, not prompt text.

---

## D. Evidence and provenance — the team layer

### D1. `craft_record` ⭐⭐

```rust
craft_record {
    claim: String,
    confidence: "measured" | "inferred",
    evidence: [ { "kind":"render", "id":"…", "revision":42 },
                { "kind":"assert", "id":"…" },
                { "kind":"resource", "uri":"vectorcraft://object/17" } ],
    note?: String,
}
```

**Reject `confidence: "measured"` with an empty `evidence` array.** That single validation is the
whole point. It is the creative analogue of "never present speculative telemetry values as
measured facts", and it cannot be talked around by a chatty model.

Persists to the session store; `craft_artifact_list` returns it alongside the files.

### D2. `craft_delegate`

```rust
craft_delegate { role: Role, brief: String, doc_ref: DocRef, expect?: String }
```

The coordinator's parallel fan-out. TimeAttack does this with `broadcast_event` + agent-to-agent
messaging; with a gateway you can make it a first-class, auditable call that carries `doc_ref` and
collects structured results.

### D3. `craft_notify_user` — elicitation as a tool

No app implements MCP `elicitation`. But Scaico has `notify_user` and `broadcast_event`, so the
gateway should too:

```rust
craft_notify_user {
    message: String,
    render?: RenderRef,        // show the user what the agent is looking at
    options: [String],
    blocking: bool,
}
```

Rendering the user's view inline is what makes this trustworthy — the human sees the actual pixels
the agent claims to be reasoning about, and can disagree.

### D4. `craft_artifact_*` — the shared namespace

```rust
craft_artifact_put { path: String, from_app?: App, kind?: String }
craft_artifact_get { id: String } → bytes or a preview render
craft_artifact_list { kind?, since_revision? } → [{ id, path, provenance, claims[] }]
```

Provenance per artifact: which agent, which tool calls, which renders, which claims. **Without
this, a multi-agent creative pipeline produces files nobody can trace.**

---

## E. Cross-app orchestration

### E1. `craft_pipeline`

```rust
craft_pipeline {
    steps: [ { app, tool, args, expect?, capture? } ],
    on_error: "stop" | "continue",
    carry: ["doc_ref", "asset_id"],
}
```

Runs a multi-app sequence with automatic snapshot-before-destructive, per-step evidence capture,
and a final contact sheet. This is where "designcraft layout → photocraft retouch → deckcraft
slide → pdfcraft export" becomes one auditable call.

### E2. `craft_app_call`

```rust
craft_app_call { app: App, method: String, params: Value }
```

Raw passthrough to any control-protocol method — `ui.inspect`, `ui.set`, `ui.pointer`, `jobs.list`,
`ui.menu.invoke`, and every method added upstream later. **The escape hatch that makes the design
future-proof: new app capabilities are available the day they ship, with no gateway change.**

---

## F. Transport (not a tool, but the enabler)

| Requirement | Why |
|---|---|
| **stdio** MCP server | Local agents. No port, no auth surface. |
| **streamable-http** MCP server with bearer tokens | **Required by the scaico.com team format.** |
| Token → tool allowlist | The `mcp_servers[].tools` field in your team JSON. Server-enforced. |
| Per-session sandbox roots | The multi-tenant version of `04-SECURITY.md` §3. Needs its own threat model. |
| Egress allow-list | If `artcraft_cloud` is enabled, restrict to `api.storyteller.ai` + the CDN. |
| Credit budget per token | Cloud generation costs money. Cap it server-side. |

---

## Complete tool list

| Tool | Category | Priority | Gap it fills |
|---|---|---|---|
| `craft_apps` | meta | P0 | Which apps exist, what each is for |
| `craft_status` | state | **P0** | One call for all-app status |
| `craft_run` | exec | **P0** | Guarded `engine.execute` |
| `craft_run_tool` | exec | **P0** | Namespaced passthrough to any app's curated tools |
| `craft_look` | **perception** | **P0** | Unified render, scope + region + LOD |
| `craft_snapshot` / `craft_restore` | safety | **P0** | The seatbelt |
| `craft_record` | evidence | **P0** | Enforces "no unbacked claims" |
| `craft_app_call` | escape | **P0** | Raw control-protocol access |
| `craft_assert` | verification | **P1** | Mechanical postconditions |
| `craft_diff` | perception | **P1** | What changed — nothing else provides this |
| `craft_contact_sheet` | perception | **P1** | N pages, one image, ~30× token saving |
| `craft_probe` | perception | **P1** | What's at this point |
| `craft_read_resource` | perception | **P1** | URI templates as a tool |
| `craft_history` | state | P1 | Undo stack |
| `craft_wait` | state | P1 | Encapsulated polling (no subscriptions exist) |
| `craft_delegate` | team | P1 | Parallel fan-out with `doc_ref` |
| `craft_notify_user` | team | P1 | Elicitation as a tool |
| `craft_artifact_*` | team | P1 | Shared namespace + provenance |
| `craft_pipeline` | orchestration | P2 | Multi-app with evidence |
| `craft_lod` | perception | P2 | Zoom pyramid |
| `craft_play` | perception | P2 | Spectrogram/waveform (SoundCraft) |
| `craft_undo` / `craft_redo` | safety | P2 | Explicit, safe exploration |

**~24 tools total.** Per-agent allowlists mean any given agent sees 8–15 of them.

---

## What to build first

**Phase 1 — make it usable at all (1–2 days)**
`craft_apps`, `craft_status`, `craft_run`, `craft_run_tool`, `craft_app_call`, stdio transport,
allowlists. Already wraps everything; proves the architecture.

**Phase 2 — make it trustworthy (2–3 days)**
`craft_look`, `craft_snapshot`/`craft_restore`, `craft_record`, `craft_assert`.
**This is where the agent stops being able to lie.** Highest value per line of code in the project.

**Phase 3 — make it economical (1–2 days)**
`craft_contact_sheet`, `craft_diff`, `craft_read_resource`, `craft_probe`, `craft_wait`.

**Phase 4 — make it a team (3–5 days)**
streamable-HTTP transport, token→allowlist, `craft_delegate`, `craft_notify_user`,
`craft_artifact_*`. Then author the team JSON files.

**Phase 5 — upstream gaps to file**
Headless render for GridCraft + SoundCraft; subscriptions; diffing in the engines;
spectrogram for SoundCraft.

---

## One sentence

The apps already give you every *action*. What they do not give you is **observation over time**
(no diff, no change notification, no zoom), **verification** (no way to assert an edit succeeded
without eyeballing pixels), and **accountability** (no way to prove a claim was measured). Those
three gaps — not the ~270 tools — are what your gateway has to build.