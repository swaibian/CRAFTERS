# 06 — Perception: How an Agent "Sees", and the Integration Layer

Companion to `01-RESEARCH-FINDINGS.md`. This document answers three questions:

1. How does an agent see what the app shows the user, **today**?
2. What is missing, and what must the gateway build?
3. What does a complete agent-integration application look like across all 12 apps?

---

## Part 1 — What exists today

### 1.1 Four perception channels, not one

This is the mental model to keep. An agent does not "see the app". It has four distinct sensors,
with different costs and different blind spots.

| Channel | Tool family | Cost | Answers |
|---|---|---|---|
| **A. Document render** | `render_preview`, `render_page`, `render_slide`, `render_frame`, `page_render`, `render`, `render_photo` | cheap, deterministic, headless-safe | *"What does the artwork look like?"* |
| **B. Window screenshot** | `ui_screenshot`, `screenshot` | expensive (full res, needs a visible window) | *"What does the whole app look like — chrome, panels, dialogs?"* |
| **C. Structured UI state** | `ui_inspect`, `doc_inspect` | cheap JSON, **the best value** | *"What is the app's state — tool, selection, zoom, dialogs, jobs, perf?"* |
| **D. Element enumeration** | `ui.elements`, `ui.widgets`, lightcraft `list_widgets`, pdfcraft AccessKit | very cheap | *"Which widgets exist and where are they?"* |

Most people designing agent integration only think about A and B. **C and D are where the real
efficiency is**, and they are the most neglected.

### 1.2 Channel A — document render

Available headless. The reliable, CI-friendly choice. Returns an MCP image content block
(`{"type":"image","data":<base64>,"mimeType":"image/png"}`).

| App | Tool | Captures | Size control |
|---|---|---|---|
| photocraft | `render_preview` / `doc_render_preview` | flattened document composite | `max_side` 1024, ceiling 2048 |
| vectorcraft | `render_preview` | one artboard | `max_side` 1–4096, default 1024 |
| lightcraft | `render_preview` / `render_photo` | one photo with develop settings + crop | `size` 16–4096, default 1024 |
| pdfcraft | `page_render` / `render_preview` | one page | `dpi` 1–600 / `max_side` 1–4096 |
| designcraft | `render_page` | one page, printing items only | `scale` px/pt |
| deckcraft | `render_slide` | one slide (`edit:true` adds placeholder prompts) | `scale`, default 960×540 |
| wordcraft | `render_page` | one page | `scale` |
| effectcraft | `render_frame` / `render_preview` | one comp frame | `max_side` 960, `transparent` |
| filmcraft | `render_frame` | one sequence frame | `max_side` 960 |
| cadcraft | `render` | the drawing, fitted to extents | `width` ≤8192, `height` ≤8192, `fit` |

**Important:** `render_page` in DesignCraft returns **printing items only** — guides, selection
and the baseline grid are excluded, so what the agent sees deliberately differs from the screen.
`deckcraft render_slide {edit:true}` adds placeholder prompts that are not in the final render.
Know which view you are asking for.

### 1.3 Channel B — window screenshot

All window captures go through `egui::ViewportCommand::Screenshot`, which returns the **client
area**: panels, canvas, ribbons, in-window menus. **The native macOS menu bar is never in the
image.** VectorCraft is the only app that even reports this (`"nativeMenuBar": bool`).

Three returned as a **path**, not an image — an easy trap:

| App | Behaviour |
|---|---|
| **gridcraft** | `screenshot` requires `path`; returns **JSON text**, never an image block |
| **cadcraft** | `screenshot` returns **JSON text**, never an image block |
| **soundcraft** | returns an image block **only when `path` is omitted**; with `path` it silently degrades to JSON text |

Occlusion handling is uneven, and it matters on macOS where occluded windows stop rendering:

| App | Strategy | Timeout |
|---|---|---|
| photocraft | `focus: true` default → `ViewportCommand::Focus` | — |
| vectorcraft | `focus: true` default | fails after ~8 s |
| designcraft | `focus: true` default | — |
| **filmcraft** | `orderFrontRegardless` on every window — orders forward **without activating**, so the user's keystrokes keep going elsewhere. Called from `ui.screenshot` *and* from the control drain whenever a `ui.*` request arrives and the UI hasn't run a pass for 0.25 s. | 10 s (doc) / 3 s + 0.25 s settle (code) |
| **lightcraft** | **No focus call.** Waits ≥3 frames / ≥120 ms and for in-flight renders; if the compositor delivers nothing in `SCREENSHOT_FALLBACK_MS = 2000`, it **re-renders the entire UI on the CPU** in a shadow egui context (the renderer keeps CPU photo copies for exactly this). `headless: true` forces it. | 2 s then CPU fallback |
| gridcraft | 100 ms + 3-frame settle | 8 s with an actionable error |
| pdfcraft | 5 s | specific error: *"the window is not being drawn (it may be hidden, minimized or covered); bring it to the front and retry"* |
| effectcraft, cadcraft, deckcraft, wordcraft, soundcraft | **nothing found** | — |

FilmCraft's `orderFrontRegardless` is the **right** pattern and should be the gateway's default
expectation: raise the app for the agent without stealing the human's keyboard focus.

**Scaling:** only photocraft, lightcraft, effectcraft and filmcraft downscale window screenshots.
`vectorcraft ui_screenshot`, `designcraft`, `gridcraft`, `cadcraft`, `deckcraft`, `wordcraft`,
`soundcraft` have **no scaling control** — you get a full-DPI window PNG. At Retina that is
~4× the tokens for no extra information. The gateway must downscale uniformly.

Budgets in PhotoCraft are a good template (`crates/automation/src/budgets.rs`):
`MAX_RESPONSE_BYTES = 8 MiB`, `MAX_PNG_BYTES = 5 MiB`, `MAX_PREVIEW_SIDE = 2048`,
`MAX_RENDER_SOURCE_PIXELS = 64 Mpx`, bridge decode capped at 8192×8192 / 16 Mpx / 64 MB alloc.

### 1.4 Channel C — structured UI state (the one to lean on)

`ui_inspect` returns a JSON object that is, for most agents, **more useful than the screenshot** —
it is exact, cheap, diffable, and text.

The richest:

| App | Notable sections beyond `ui`/`window`/`perf` |
|---|---|
| **lightcraft** | `canvasRect`, `imageRect`, `scroll`, `selection[]`, `activeMask`, `widgetCount`, **`perf`** (frameMs, renderQueue, rendersInFlight, pendingSlots, mergeRunning, rendersDone, gpu, gpuFallback), **`loupe{photo,source,pending,region{full,window,pending}}`**, `hoverPreview`, `tasks[]`, **`activity[]`**, `faceScan{pace,focused,pending,indexed}`, `unsaved`, `scan`, `export{running,last}`, `import`, `fileDialogs[]`, **`memory`** (engine + renderer cache bytes) |
| **photocraft** | `tool`, **`toolOptions`** (eyedropper + crop-shield), **`views[]`** (per-window zoom/centre/rotation/fit_pending), **`dialogs[]`** with **full field state**, `window`, `canvasToolMenu`, `layerMenu`, `brushPicker{pos,size,list{...}}`, **`magnetic`** (lasso path/anchors/live/mode), `textEdit`, `typeTransform`, `docking`, `view`, `notices`, `gpuFallbackNotice`, `kysOffer`, `jobs`, **`cameraRaw`** (histogram, vectorscope, pointer readouts, curve/viewport rects), `perf.timings.gpuInfo` |
| **pdfcraft** | `active{zoom_percent, fit, layout, viewport, **pages_on_screen[{page,rect}]**, selected_comment, comment_composer_open, page_errors, raster_memory}`, `combine{thumbnails}`, `dialog`, `quick_tool`, `home`, `mode`, `palette_open`, **`progress{label,fraction}`**, `password_prompt`, `close_prompt` |
| **effectcraft** | `ui.viewer{zoom,pan,res,transparency_grid,grid,rulers,guides}`, **`ui.timeline{…}`**, `elements` (count), **`keyboardFocus{id,rect,automationId,registryCandidates[]}`**, `dialog`, `playing`, `time`, `activeComp`, `selectedLayers`, `selectedKeys`, `windowFocused` |
| **wordcraft** | `view`, `canvasRect`, **`pages[]`** (screen rect per page), `scale`, **`caret{x,y,h}`**, `balloons[{id,rect}]`, `dialog`, `focused` |
| **deckcraft** | `canvasRect`, `slideRect`, `canvasScale`, `showing{slide,step,ended}`, `dialog` |
| **cadcraft** | `canvasRect`, `view{center,height}`, **`cursor`** (world coords of last pointer), `snap{point,mode}`, `focus{id,label,role,keyboardInput}` |
| **vectorcraft** | `tool`, `taskBar{pinned,rect}`, `freeTransformWidget{rect}`, `view`, **`canvasRect`**, `documents[]`, `nativeMenuBar`, **`background[]`**, **`fileDialog`** (a native dialog is blocking a command) |
| **filmcraft** | **`keyboardFocus{widgetId,elementIds[],label,active}`**, `input{mode,nativeWindowFocused,effectiveWindowFocused}`, **`playback{playing,speed,loop,audioClock,dropped,shown,preroll}`**, `playhead`, `activeSequence`, `selection`, `elements`, `dialog` |
| **designcraft** | `tool`, `view{zoom,origin,fitted,rotation}`, `canvasRect`, `documents`, `currentPage`, `dialog` |
| gridcraft | `grid` (cell rect), `scroll`, `editor{cell,text,formulaBar,point}`, `dialog`, `backstage`, `message`, `selectedChart` — **but no MCP tool reaches it** |
| **soundcraft** | `window_size`, `playing`, `position`, `dialog`, `frame_ms`, `audio_device`, `edit_layout` (timeline + track row rects) — **the thinnest of the twelve** |

**Use C as the default sensing channel.** Reserve B for "show me what the user sees" moments and
for verifying chrome that has no structured representation.

### 1.5 Channel D — element enumeration (the cheapest, least finished)

| App | Mechanism | Coverage |
|---|---|---|
| **pdfcraft** | **Full AccessKit tree** — caches `platform_output.accesskit_update` every frame, walks from the root, emits `{widgets:[{id,role,depth,enabled,clickable,focusable,label,value,description,rect,toggled,selected,focused}],count,truncated}`. Filters: `query`, `role`, `focused`, `limit` (default 500). Clicks drive widgets via `accesskit::ActionRequest`, not pointer synthesis. | **Complete — every widget with an AccessKit node** |
| **lightcraft** | `ui.widgets {filter?}` → `{id, rect:[x,y,w,h]}`, namespaced ids (`slider:`, `section:`, `button:`, `icon:`, `dropdown:`, `field:`, `crumb:`, `group:`, `film:`, …) | Broad but opt-in |
| **effectcraft** | `ui.elements {prefix?}` over an `app.auto` registry; stable ids (`tools.Selection`, `panel.Timeline`, `timeline.layer.<id>.bar`, `timeline.prop.<uid>.stopwatch`, `effects.item.<name>`, …) | Opt-in |
| **filmcraft** | `ui.elements {prefix?}`, same pattern (`timeline.clip.<id>`, `tools.Razor`, `program.transport.playback.toggle`) | Opt-in |
| **cadcraft** | `ui.elements {label?,role?,focused?}` over `record_widget(...)`, cap 2048 | Opt-in |
| photocraft, vectorcraft, designcraft, gridcraft, deckcraft, wordcraft, soundcraft | **none** | — |

MCP reachability: lightcraft (`list_widgets`), filmcraft (`ui_elements`) and effectcraft
(`ui_elements`) expose it as tools. **pdfcraft's AccessKit tree is not exposed via MCP at all** —
its MCP server is headless-only. photocraft, filmcraft, effectcraft and deckcraft have a generic
`control_call`/`control`/`ui_control`/`call_app` passthrough, so raw methods are reachable;
vectorcraft, lightcraft, designcraft, gridcraft, cadcraft, wordcraft and soundcraft do not.

### 1.6 Accessibility trees: enabled everywhere, read by almost nobody

The `accesskit` feature **is enabled in the desktop and web binaries of all 12 apps**. Every app
publishes an OS-level accessibility tree to screen readers. But only **pdfcraft** reads that tree
back out and exposes it to an agent. The other apps only assert on `accesskit_update` in
`#[cfg(test)]` blocks.

**This is the single biggest missed opportunity in the whole fleet.** An AccessKit tree is a
structured, labelled, positioned description of every widget — cheaper and more accurate than a
screenshot, and it is already being computed. An agent that can read it can find and click any
control by label instead of pixel-hunting.

### 1.7 Numeric perception channels (better than pixels for measurement)

| App | Channel | Detail |
|---|---|---|
| **filmcraft** | engine command `scopes.read` | The richest numeric channel in the fleet. `{scopes:[waveform,parade,histogram,vectorscopeYuv,vectorscopeHls], waveformType, paradeType, colorSpace, clamp, columns, peaks, bins, scale, time}` → `{time,frame,samples,colorSpace,matrix,clamp,unit,stats}` plus per-scope traces / peak bins / vectorscope mean+peaks. **An agent grading an image should read this, not look at it.** |
| **photocraft** | `ui.inspect.cameraRaw` | Full RGB histograms, `vectorscope`, `pointerReadout`, `samplerReadouts[]`, `curveState`, `curveRect`, `previewRect`, `vectorscopeRect`, `scopeRect`, `viewportRect`, `zoom`, `hasScopeSelection` |
| photocraft | `document.sampleColor {x,y,size,sampleLayer}` → `[r,g,b,a]` | `size` = `point` or 1/3/5/11/31/51/101 — the real Eyedropper squares. Also `document.pixel {x,y}`. |
| **lightcraft** | `ui.render` without a path → `{width,height,histogram}` | `Histogram{r,g,b,luma,total,hdr?}` — **but the MCP `render_photo`/`render_preview` tools always pass a temp path and discard it.** Only reachable over the raw control channel. |
| **gridcraft** | `selection.stats {count,sum,average,min,max}` | Via `execute_command` |
| **pdfcraft** | `ocr_recognize {pages,dpi,skip_text_pages}` | Recognised text per page. `text_extract {rect}` reads text inside a page rectangle. |
| **soundcraft** | `bounce_mix` returns peak dBFS + integrated LUFS | The only numeric audio readout; not a live meter |

### 1.8 Coordinate systems

| App | Pointer input space | Mapping exposed? |
|---|---|---|
| **photocraft** | `ui.pointer` = **document pixels**; `ui.click`/`ui.move` = screen points | zoom + centre yes, **canvas rect NO** |
| **vectorcraft** | `pointer_gesture` = document points (`space:"doc"`) or screen (`space:"screen"`) | `canvasRect` + `view` ✓ |
| **lightcraft** | `pointer_gesture` = **normalized 0..1** of the displayed photo frame; `click`/`drag` = screen points | `canvasRect`, `imageRect`, `loupe.region` ✓ |
| **designcraft** | `pointer` = spread points or screen | `canvasRect` + `view{zoom,origin,rotation}` ✓ |
| **effectcraft** | `click`/`move`/`drag` = screen points | **no canvas rect**, but `ui.viewer.locate {x,y}` (comp px → screen) and `ui.viewer.hit {x,y}` (screen → comp px) substitute |
| **filmcraft** | screen points | **no viewer rect**, but `ui.timeline.hit {x,y}` / `ui.timeline.locate {clip,edge?}` |
| **gridcraft** | window points; `ui.cell.click {cell}` takes an **A1 reference** | `grid` rect + `scroll` — but not via MCP |
| **cadcraft** | `ui_click {x,y,space}` = **world coords** or screen | `canvasRect`, `view`, `cursor`, `snap` ✓ |
| **deckcraft** | `pointer` = slide points; click = window points | `canvasRect`, `slideRect`, `canvasScale` ✓ |
| **wordcraft** | screen points; `ui.clickText {page,x,y}` = page position in points | `canvasRect`, `pages[]`, `scale`, `caret` ✓ |
| **pdfcraft** | logical points | `active.viewport` + **`pages_on_screen[{page,rect}]`** ✓ |
| soundcraft | window points | `edit_layout` for the timeline only |

All egui coordinates are **logical points**, not device pixels. `pixelsPerPoint` is reported by
photocraft, lightcraft, effectcraft, filmcraft and pdfcraft — **not** by vectorcraft, designcraft,
gridcraft, cadcraft, deckcraft, wordcraft or soundcraft.

---

## Part 2 — What is missing, and what the gateway must build

### 2.1 Gaps that apply everywhere

1. **No canvas-region capture.** There is no tool that returns "the pixels of the canvas as the
   user currently sees them, with overlays, guides, marching ants and the brush cursor, clipped
   to the canvas". `ui_screenshot` returns the whole window; `render_preview` returns the
   document without overlays. **For a graphics app, this is the primitive agents actually want.**
   → *Gateway must build it, by cropping the window screenshot to `canvasRect`.*

2. **No pointer position.** Only cadcraft reports `ui.inspect.cursor`. No app reports the cursor
   in screen points, and no app reports hover state or what a right-click would show.

3. **No on-screen text channel.** Nothing OCRs or reports the UI's glyphs. LightCraft has
   `HeadlessView::painted_text()` (`crates/ui-egui/src/headless.rs:191`) that could list every
   string drawn in a frame — it is **test-only and unwired**. Without it an agent cannot read a
   tooltip, an open menu, a disabled reason.

4. **No z-order / topmost surface.** Apps report *which* dialogs exist, never which one is modal
   or receives input.

5. **No image diffing anywhere.** The only structural support is pdfcraft's `doc_compare
   {doc, other, visual: true}` → regions that differ visually as `{page, rect}`.
   → *Gateway must build `see_diff`.*

6. **No live-screen pixel sampling.** photocraft can sample the *document*; nothing can read the
   colour of what is actually rendered on screen.

7. **Everything is a synchronous poll.** `resources/subscribe` is `false` in every server. There
   is no `notifications/tools/list_changed`, no app-event push. A long agent loop spends its
   budget on `ui_inspect` round-trips.
   → *Gateway must build `watch`.*

8. **No uniform scaling.** 8 of the window screenshots cannot be downscaled.

### 2.2 App-specific misses worth designing around

- **photocraft**: no canvas rect (so document↔screen conversion is impossible despite
  `ui.pointer` being document-space); the **Camera Raw dialog is invisible** (separate OS window —
  `ui.screenshot` shows a dimmed main window); main-window Histogram/Info panel contents are not
  reported at all.
- **pdfcraft**: the AccessKit tree and `ui.screenshot {region}` are **control-channel only** — the
  cheapest perception channels in the fleet, unreachable from MCP. Its MCP server is headless-only,
  so an MCP agent never sees the window.
- **gridcraft**: `ui_inspect` is not an MCP tool. `screenshot` returns JSON, not an image.
- **soundcraft**: the thinnest `ui.inspect`; no meters; screenshot degrades to JSON with a `path`.
- **filmcraft**: no viewer↔screen mapping (unlike effectcraft's `locate`/`hit`).
- **effectcraft / filmcraft / cadcraft**: element registries are opt-in, so uncaptured widgets
  cannot be clicked by id.
- **lightcraft**: histogram unreachable via MCP; no explicit pixels-per-photo-pixel factor.

---

## Part 3 — The integration layer

### 3.1 A hard constraint discovered in the Scaico team format

The Scaico example references MCP servers as:

```json
"mcp_servers": [{ "url": "https://…/mcp/v2/mcp", "token": "…", "transport": "streamable_http",
                  "tools": [ … ] }]
```

**`streamable_http`, not stdio.** A hosted team cannot spawn local processes. Therefore:

> **The gateway must expose Streamable HTTP as its primary transport**, with bearer-token auth.
> stdio remains useful for local interactive clients, but it is not the Scaico path.

That also forces **flat, globally-unique tool names** — Scaico addresses tools by bare string
(`"tools": ["get_lap_detail", …]`), so `see_window` must not collide across namespaces. This is
why the naming below is flat and prefixed rather than nested.

### 3.2 Gateway tool inventory

**Perception — `see_*`**

| Tool | Purpose | Replaces / adds |
|---|---|---|
| `see_window` | Whole-window capture, **uniformly downscaled** to a token budget | `ui_screenshot`/`screenshot` on all 12; fixes the 8 apps with no scaling |
| `see_canvas` | **The canvas region of the live screen**, cropped to `canvasRect` | **NEW — the missing primitive** |
| `see_document` | Document render (headless-safe, deterministic) | `render_preview`/`render_page`/`render_slide`/`render_frame`/`page_render`/`render` |
| `see_region` | Arbitrary rect in screen points | effectcraft/filmcraft panel+id; pdfcraft region; **NEW** for the other 9 |
| `see_element` | Capture by element id / label / role | **NEW** — uses the widget registries |
| `see_element_state` | Element rect, role, label, value, toggled, selected, focused, enabled | unifies `ui.elements` / `ui.widgets` / pdfcraft AccessKit |
| `see_diff` | Perceptual diff of two captures → changed regions + a % | **NEW** — generalises pdfcraft `doc_compare` |
| `see_text` | On-screen glyph strings in a region | **NEW** — wires lightcraft's `painted_text` idea app-wide |
| `see_pointer` | Cursor position in screen + document space | **NEW** — only cadcraft has it today |
| `see_scopes` | Histogram / waveform / vectorscope / colour sample | filmcraft `scopes.read`, photocraft `cameraRaw.*`, lightcraft histogram, photocraft `sampleColor` |

**State — `query_*`**

| Tool | Purpose |
|---|---|
| `query_ui` | Normalised `ui_inspect` (adds `canvasRect` everywhere; synthesises it where missing) |
| `query_document` | Document structure (layer tree, history, selection) |
| `query_commands` | The command registry — the universal discovery tool |
| `query_jobs` | Running/finished jobs with progress |
| `query_map` | **Coordinate mapping**: document ↔ screen for the active view |
| `query_tools` | The app's own MCP tool list (proxy `tools/list`) |

**Control — `act_*`**

| Tool | Purpose |
|---|---|
| `act_command` | Run any engine command (`{app, id, params}`) — the universal verb |
| `act_batch` | Ordered steps with `$N.path` result references; optional `atomic` |
| `act_pointer` | Document- or screen-space gesture with pressure/tilt/modifiers |
| `act_click` / `act_key` / `act_type` | Screen-point and keyboard input |
| `act_element` | Click/focus **by element id** (AccessKit `ActionRequest` where available) |
| `act_ui` | Change UI state (tool, panels, zoom, theme, dock) |
| `act_menu` | Invoke a menu item like a click |
| `act_dialog` | `set` / `confirm` / `cancel` on the open dialog |

**Lifecycle — `doc_*` / `job_*`**

`doc_open`, `doc_list`, `doc_save`, `doc_close`, `doc_export`,
`job_wait`, `job_cancel`

**Coordination — `team_*`** (the agentic-team primitives; see `07-SCAICO-TEAMS.md`)

`team_apps` (who owns what, online/offline), `team_claim` / `team_release` (per-app mutex),
`team_handoff` (pass state), `team_blackboard_read` / `team_blackboard_write`,
`team_notify` (push to the leader), `team_checkpoint` (snapshot + named undo point),
`team_asset_put` / `team_asset_get` / `team_asset_list`

**Cloud — `cloud_*`**

`cloud_models`, `cloud_cost`, `cloud_generate`, `cloud_job`, `cloud_upload`, `cloud_download`

Total: ~40 tools. Deliberately flat and uniquely named because Scaico addresses them by string.

### 3.3 Why the coordination primitives are not optional

A GUI app has **one selection, one active layer, one undo stack, one canvas**. Two agents driving
the same app concurrently will corrupt each other's work in ways that are very hard to debug.

So the gateway must own:

- **A per-app mutex** (`team_claim`). One agent owns an app at a time. This turns an impossible
  problem into a queue.
- **Named checkpoints** (`team_checkpoint`). Every agent marks its intent before an edit batch and
  can be rolled back — the agentic equivalent of a git branch per agent.
- **A shared asset namespace** (`team_asset_*`). The only channel between agents that carries
  bytes, with provenance: which app, which call, when.
- **A blackboard** (`team_blackboard_*`). Derived state — extracted text, measured values,
  decisions — so specialists do not each re-derive the same context.
- **Push, not poll** (`team_notify`). Plus `watch(app, condition, timeout)` on the gateway side so
  "wait until the render finishes" is one call, not 200 `ui_inspect` round-trips.

### 3.4 Session model

```text
Agent  ──streamable_http──►  crafters-gateway  (one process per host, many sessions)
                              │
                              ├─ session registry, per-session roots + budgets
                              ├─ app instances (lazy headless children, or bridged GUIs)
                              ├─ per-app mutex + checkpoint log
                              ├─ shared asset store (content-addressed, provenance-tracked)
                              └─ Scaico team router: tool allowlists per agent
```

Per session: its own `read_root`/`write_root`, its own headless app processes, its own asset
namespace, its own credit budget. Two teams on one host must not see each other's files.

---

## Part 4 — The "agentic application" pattern

The design principle that makes these 12 apps composable by a team:

> **Each app is a pure, headless, file-in/file-out function. Agents should treat them as such and
> reserve live-GUI mode for verification and human-in-the-loop moments.**

A production pipeline becomes:

```text
wordcraft   extract text ──► asset:text/*
                          ├─► lightcraft  develop RAW      ──► asset:photo/*
                          ├─► vectorcraft build logo       ──► asset:vector/*
                          ├─► effectcraft compose frames   ──► asset:frame/*
                          ├─► soundcraft  score            ──► asset:audio/*
                          └─► designcraft lay out pages    ──► asset:layout/*

Final: designcraft/deckcraft/wordcraft assemble ◄── assets
       photocraft retouch ◄── assets
       pdfcraft export ◄── final documents
       ── ONE bridge-mode verification pass per deliverable ──
```

~90% headless (fast, deterministic, parallelisable, no display). ~10% bridged: open the finished
artifact in the real GUI, `see_window`, and check it against the brief.

### 4.1 Bridging the perception gap cheaply

The most valuable single addition, because it removes the occlusion problem class entirely:

```text
agent wants to see the live app
   └─ see_window          → full window screenshot (downscaled)
   └─ see_canvas          → canvas region only, cropped from the same capture
   └─ see_element_state   → what's in every panel, as JSON (no pixels needed)
   └─ see_text            → what strings the UI is currently showing
```

`see_element_state` needs no window at all — it reads the app's state, so it works even when the
window is occluded, minimised, or on another display. That makes it the **default** perception
channel for anything other than "what does it look like".

---

## Part 5 — Implementation notes

**Capture pipeline (build once, use 12 times):**

1. Pick a target: `window` | `canvas` | `document` | `region` | `element`.
2. Resolve to (a) a capture call and (b) an optional crop rect:
   - `window` → `ui.screenshot` / `ui_screenshot`, no crop
   - `canvas` → `ui.screenshot` + crop to `canvasRect`
   - `document` → `render_preview`/`render_page`/…, no crop
   - `region` → `ui.screenshot` + crop to the given rect
   - `element` → look up the rect in the element registry, then `region`
3. Downscale uniformly to the token budget (the 8 apps that cannot do it themselves).
4. Return `{ image, meta }` where `meta` carries app, mode (headless/bridge), capture source,
   crop rect, final pixel size, scale factor, and any warning (occlusion fallback, CPU re-render,
   focus raised).

Step 4 is what makes this consistent. Step 2's `canvas` case is the new work; `canvasRect` is
present in 7 apps and must be synthesised for photocraft, effectcraft, filmcraft, gridcraft and
soundcraft (lightcraft's `imageRect`, wordcraft's `pages[]`, pdfcraft's `pages_on_screen` and
effectcraft's `viewer.locate` give enough to derive it).

**Accessibility, if you want the cheapest channel:** enable the `accesskit` feature (already on),
cache `platform_output.accesskit_update` per frame as pdfcraft already does, and expose it as
`see_element_state`. This is ~200 lines per app and would give every app pdfcraft's Channel-D
completeness. Worth an upstream PR.

**Never auto-retry a write.** PhotoCraft's rule: a transport failure mid-request may mean the edit
landed. Retry pure reads only.

**Respect the human.** FilmCraft's `orderFrontRegardless` pattern — order the window forward
without activating it — is the correct behaviour when an agent touches a GUI someone is using.