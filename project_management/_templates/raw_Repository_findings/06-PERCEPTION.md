# 06 — Perception: How an Agent "Sees"

Answers the question: *for a tool like PhotoCraft, how does the agent see what the program shows
the user?*

---

## The short answer

There are **three distinct tiers** of seeing, and they are not interchangeable. Confusing them is
the single biggest design mistake available here.

| Tier | What it shows | Transport | Headless? | Cost |
|---|---|---|---|---|
| **1. Structure** | The document *model*: layers, history, selection, bounds, ids | JSON | ✅ yes | ~1–20 k tokens |
| **2. Content** | The *work product* rendered to pixels: the flattened image, the slide, the page | PNG image content | ✅ mostly (10/12) | ~1–30 k tokens |
| **3. Window** | The *running application*: panels, dock, dialogs, menus, cursor, chrome | PNG image content | ❌ **bridge only** | ~30–80 k tokens |

Most agents should live on **Tier 1 + Tier 2**. Tier 3 is for the cases only Tier 3 can answer:
*"a dialog is open and blocking"*, *"what does the user actually see"*, *"is the crop tool's
overlay up"*.

### The rule

> **Tier 2 renders the document. Tier 3 photographs the application.**
> They are not the same thing, and Tier 3 is far more expensive and far less useful.

PhotoCraft is explicit that in bridge mode `render_preview` *degrades to a window screenshot*
(`server.rs:599`, *"bridge mode: app window screenshot"*) — because it cannot reach the document
renderer through the control channel. So even upstream treats Tier 3 as the fallback, not the goal.

---

## Tier 1 — Structure (JSON)

Available everywhere, headless included. The cheapest reliable perception.

| App | Tool | Returns |
|---|---|---|
| photocraft | `doc_inspect {index?}` | layer tree top-to-bottom, history, selection, channels, `selectedLayers` |
| pdfcraft | `doc_inspect {doc?}` | metadata, page sizes, bookmarks, annotations, form fields, links, layers, fonts |
| filmcraft | `doc_inspect`, `project_inspect`, `sequence_inspect` | three scopes: document / project / timeline |
| vectorcraft | `doc_inspect {depth?, childLimit?}` | artboards, layer tree, selection, history |
| lightcraft | `doc_inspect` | catalogue, develop state, selection |
| designcraft | `inspect_document` | frames, stories, styles |
| gridcraft | `inspect_workbook` | sheets, ranges, formulas, names |
| cadcraft | `inspect_drawing {entities?, limit?}` | entity counts, extents, layers, blocks, selection, undo history |
| deckcraft | `inspect_document`, `inspect_slide` | deck + one slide (shapes, text, placeholders, animations) |
| soundcraft | `inspect_session {detail: summary\|full}` | tracks, clips, busses, sends, automation, markers |
| wordcraft | `inspect_document` | sections, styles, tracked changes |

Underneath: `engine.commands` / `command_list` (the registry with param docs + enabled state) and
`ui.inspect` (Tier 3 state as JSON, bridge only).

**Tier 1 is authoritative and exact.** Use it to verify Tier 2 claims, not the other way round.

---

## Tier 2 — Content (pixels)

This is "what the document looks like", rendered by the engine's own renderer. **This is what you
want an agent to reason about.**

| App | Tool | Headless | Notes |
|---|---|---|---|
| photocraft | `doc_render_preview {index?, max_side?}` | ✅ | `max_side` default 1024, max 2048. `render_preview` is the alias |
| pdfcraft | `render_preview {doc?, page?, max_side?}`, `page_render` | ✅ | `page` 1-based, `max_side` 1–4096 default 1024 |
| filmcraft | `render_preview`, `render_frame` | ✅ | frame = the atomic unit |
| vectorcraft | `render_preview {max_side?, artboard?}` | ✅ | `artboard` 0-based; **falls back to window screenshot only when `window:true`** |
| lightcraft | `render_preview`, `render_photo` | ✅ | has its own `base64.rs` module for inline images |
| designcraft | `render_page` | ✅ | page = the atomic unit |
| effectcraft | `render_preview`, `render_frame`, `render_with` | ✅ | |
| cadcraft | `render {width?, height?, fit?, path?}` | ✅ | **best headless raster in the org** — see below |
| deckcraft | `render_slide` | ✅ | slide = the atomic unit |
| wordcraft | `render_page` | ✅ | |
| **gridcraft** | ❌ **none** | — | `screenshot` is explicitly *"Desktop app only"* |
| **soundcraft** | ❌ **none** | — | `screenshot` is `APP_ONLY` |

### ⚠️ Two real gaps

**GridCraft and SoundCraft cannot be seen at all in headless mode.** GridCraft's headless backend
rejects every `ui.*` method with `NO_UI` (`headless.rs:75`); SoundCraft's `screenshot` is
`APP_ONLY`. A headless GridCraft agent can read and write cells and inspect the workbook JSON,
but **cannot see a rendered sheet** — including, notably, **cannot see a chart it just inserted**,
despite `insert_chart` existing.

**SoundCraft's analogue is audio, not pixels**: `bounce_mix` returns peak dBFS and integrated LUFS.
That is a *measurement*, not a *perception*. There is no waveform, no spectrogram, no
"play it back and tell me what it sounds like." This is arguably worse than GridCraft's gap,
because audio quality is fundamentally perceptual.

### CADCraft's `render` — the model to copy

```rust
// cadcraft/crates/mcp/src/backend.rs:206 — answered by the IN-PROCESS backend
"ui.render" => {
    let w = …clamp(16.0, 8192.0);
    let h = …clamp(16.0, 8192.0);
    let list = cadcraft_render::build(&st.doc, &st.space, &…Options::default());
    let view = if fit { View::fit(&list.bounds, w, h, 0.05) } else { … };
```

A headless CPU rasterizer with explicit size clamping and fit-to-extents, returning
`{"pngBase64": …}` which the MCP layer wraps as `{"type":"image","data":…,"mimeType":"image/png"}`.

**Every app should have this.** CADCraft's tool list is also *conditional on the backend*:

```rust
if has_ui {
    tools.push(screenshot); tools.push(ui_inspect); tools.push(ui_click);
}
```

So a headless client is never offered a tool that will fail. **Copy this.** Do not advertise
bridge-only tools to a headless agent.

---

## Tier 3 — Window (what the user sees)

`ui_screenshot` / `screenshot` / `ui.screenshot`. **Bridge only in all 12 apps.**

Requires: `<app> --control <port>` running with a live window, and the CLI in `--bridge`/`--connect`
mode. Then:

| App | Tool |
|---|---|
| photocraft | `ui_screenshot {max_side?}` |
| vectorcraft, lightcraft | `screenshot`, `ui_screenshot` |
| designcraft, gridcraft, cadcraft, deckcraft, wordcraft | `screenshot {path?}` |
| soundcraft | `screenshot {path?}` (`APP_ONLY`) |
| effectcraft | `screenshot` |
| filmcraft | `ui_screenshot` |
| pdfcraft | ❌ none — use `pdfcraft-cli ui --control FILE` |

Useful behavioural detail from PhotoCraft: `ui.screenshot` **raises the window first** (default),
because occluded macOS windows stop rendering. And a screenshot of a window with **no path** comes
back as base64 PNG in the reply; with a path it is written under the automation write root.

`ui_inspect` / `ui.inspect` gives the same information *as JSON* — panels, dock, dialogs, windows,
`toolOptions`, running jobs, GPU info, notices. **Always prefer `ui_inspect` over a screenshot when
the question is "what state is the UI in".** It is 50× cheaper and exact.

---

## The fourth path you have not been told about: MCP **resources**

**10 of 12 apps implement MCP resources with URI templates.** This is the most under-used
perception surface in the whole ecosystem, and it is the right answer to "make content and current
status available to the agent".

### The full resource surface

| App | Resources |
|---|---|
| **vectorcraft** | `://document`, `://document/json`, `://commands`, and templates **`://object/{id}`**, **`://command/{id}`**, **`://effect/{id}`**, **`://swatch/{name}`** |
| **pdfcraft** | `://document`, `://commands`, and templates **`://doc/{doc}/info`**, **`://doc/{doc}/text`**, **`://doc/{doc}/page/{page}/text`**, **`://doc/{doc}/page/{page}/image{?dpi}`** ← **a page as an image, addressed by URI** |
| **lightcraft** | `://document`, `://commands`, `://library`, `://photos`, **`://photo/active`**, **`://develop/active`**, `://controls` |
| gridcraft | `://workbook`, `://commands`, `://functions` |
| photocraft | `photocraft://document`, `photocraft://commands` |
| filmcraft, effectcraft | `://document`, `://commands` |
| designcraft, deckcraft, wordcraft | `://document`, `://commands` |
| cadcraft | `://drawing`, `://commands` |
| soundcraft | `://session`, `://commands` |

### Why the templates are the important part

VectorCraft's design note says it outright
(`crates/mcp/src/resources.rs:1-8`):

> *"The templates matter for long sessions. `vectorcraft://document/json` returns the whole model,
> which on a real document is thousands of lines an agent pays for again on every change; the
> templates hand out one object, one command definition or one effect's parameters instead."*

That is **exactly** the problem, already solved, upstream, by the people who wrote the apps:

- **Templated resources scale to large documents** in a way no flat tool can. A PSD with 400
  layers is one `object/{id}` read, not a 40,000-line dump.
- **`pdfcraft://doc/3/page/2/image?dpi=36` returns a page as an image through the resource
  protocol** — a *low-DPI* default, which is the correct instinct. Read structure cheaply; only
  render pixels when you must.
- **Resources are read-only by protocol.** Safer than tools for anything an agent only needs to
  observe.
- **`://commands` is a live, addressable command catalog** — the agent can read exactly one
  command's definition when it needs it, without a `tools/call` round trip.

**Only 3 of 12 apps ship MCP prompts** (vectorcraft, effectcraft, gridcraft). Prompts are the
natural home for "here is how a professional uses this app" workflows; the org has barely used
them.

---

## What is missing, across all 12 apps

I found **no implementation of any of these in any app**:

| Missing MCP capability | Consequence |
|---|---|
| `resources/subscribe` + `resources/updated` | **No push.** The agent must poll. A long render gives it nothing unless it asks. |
| `sampling/createMessage` | The server cannot ask the client's model a question mid-call (e.g. "which of these three crops looks better?") |
| `elicitation/create` | The server cannot ask the *human* a question mid-call |
| Any **diff** primitive | Nothing computes "what changed between revision N and N+1". The agent re-reads and re-renders everything. |
| **Region / crop** render | Almost nothing can render just the region that changed. CADCraft has width/height/fit only. |
| **Level-of-detail / zoom pyramid** | No way to "look closer" without re-rendering the whole thing |
| **Contact sheet / multi-page** | Reviewing 20 slides costs 20 tool calls and 20 images |
| Any headless visual for GridCraft, SoundCraft | See §Tier 2 |

Progress notifications *are* implemented in 9/12 apps (`_meta.progressToken` →
`notifications/progress`), throttled to ≤10/s with a `total`, and `ping` stays responsive during a
render. PhotoCraft also supports `notifications/cancelled` with frame-boundary stops and scoped
file cleanup. So long-running work is visible — it's just that the agent has to know to ask.

---

## The honest picture

| Question | Answer |
|---|---|
| Can an agent see a PhotoCraft canvas headless? | **Yes** — `doc_render_preview` |
| Can it see the running PhotoCraft window? | **Yes, bridge only** — `ui_screenshot` |
| Can it see *what changed* since its last look? | **No** — nothing computes this |
| Can it see just the edited region? | **No** |
| Can it see 20 slides at once? | **No** |
| Can it be told "you changed"? | **No** — no subscriptions |
| Can it see a GridCraft sheet headless? | **No** |
| Can it hear what SoundCraft produced headless? | **No** — only LUFS/peak numbers |

That gap list is the specification for your gateway. See `08-REQUIRED-TOOLS.md`.

---

## Design rules that follow

1. **Default to Tier 1, escalate to Tier 2.** Structure is cheap and exact; verify with pixels
   only where the claim is visual.
2. **Never use Tier 3 to answer a state question.** Use `ui_inspect`. Screenshot only when the
   question is genuinely "what does this look like".
3. **Never show the agent a tool that will fail.** Copy CADCraft's `has_ui`-conditional tool list.
4. **Prefer resources over tools for read paths**, and expose the URI templates (`object/{id}`,
   `page/{p}/image{?dpi}`) — they are the scaling answer.
5. **Render at the lowest DPI that answers the question.** PdfCraft's `?dpi=36` default is the
   right instinct; match it.
6. **Every visual claim must be traceable to a specific render call.** This is the discipline in
   your Scaico team file ("never present speculative telemetry values as measured facts"), applied
   to pixels. Enforce it mechanically — see `08-REQUIRED-TOOLS.md` §D.