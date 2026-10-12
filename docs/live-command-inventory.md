# Live command inventory — photocraft (verified against the running app)

**Ground truth:** the running `photocraft` desktop app's control channel (`127.0.0.1:7878`,
`--control-token-file /var/folders/…/crafter-photocraft-na80coja.token`), queried 2026-10-12.
**818 engine commands** returned by `engine.commands`. Raw dump: [`live-command-registry.json`](live-command-registry.json)
(that file also carries the exact request, auth handshake and capture notes).
Source cross-check: `~/Downloads/CRAFT/photocraft-main` (workspace version `0.5.0`;
the wire exposes no version method).

---

## How to call

**Transport:** newline-delimited JSON over TCP loopback. First frame on every connection is auth:

```json
{"id": "auth", "method": "auth", "params": {"token": "<64-hex from --control-token-file>"}}
→ {"id": "auth", "ok": true, "result": {"authenticated": true}}
```

**Run a command** — the envelope is `{"id", "method", "params"}` where `method` is
`"engine.execute"` and `params` is `{"command": "<bare id>", "params": {…}}`:

```json
{"id": 3, "method": "engine.execute", "params": {"command": "document.inspect", "params": {}}}
→ {"id": 3, "ok": true, "result": {"width": 1024, "height": 1024, "layers": [...], ...}}
```

Rules (verified against `crates/ui-egui/src/control.rs` + `crates/automation/src/rpc.rs` and
with live probes):

- `command` must be a **bare id string** — never a stringified/nested envelope (see Anomaly log).
  The desktop also accepts `"id"` as an alias for `"command"` (control.rs:168).
- `params` must be a **JSON object** of the command's own parameters. Omitted or `{}` runs the
  command with its documented defaults. `"params"` is optional at the envelope level too.
- `"wait": false` (optional) starts job-capable commands (filters, Content-Aware Fill, Photomerge…)
  as background jobs → `{"job": n, "pending": true}`, poll `jobs.list`, stop with `jobs.cancel`.
  Default `true` waits for the result.
- **Dialog convention:** a label ending in `…` (U+2026) opens a dialog **in the UI menus only**.
  `engine.execute` is programmatic and runs such commands **headlessly with default params** —
  it never opens a dialog (control.rs:175-179; regression test `engine_execute_runs_with_defaults_but_menu_invoke_opens_the_dialog`).
  `ui.menu.invoke` is the dialog-opening spelling if the agent wants the modal.
- **Discovery:** `{"id": 1, "method": "engine.commands", "params": {}}` → `result` is a bare
  JSON array of entries. Each entry has **exactly these fields**:

  | field | meaning |
  |---|---|
  | `id` | stable command id (authoritative) |
  | `label` | menu label; trailing `…` = dialog command |
  | `menu` | menu path array, e.g. `["Layer", "New"]`; `[]` = not in menus |
  | `shortcut` | egui-style default shortcut or `null` |
  | `params` | human/agent-readable JSON-ish **string** doc (not a schema) |
  | `enabled` | `false` = listed but not runnable in the current session state |

  **Desktop quirk:** the desktop control channel **ignores `filter`** on `engine.commands`
  (control.rs:183 wraps `command.list` with empty params) — verified live: `{"filter":"blend"}`
  and `{"filter":"zzzNoMatchzzz"}` both return all 818 entries. Filter client-side. The
  headless server (`crates/automation/src/rpc.rs`) does honor `filter` (id+label substring).
  UI-menu-only ids (`view.zoomIn`, `file.clearRecent`, `window.theme.*`, `help.*` — 800 of them
  from `{"method": "ui.menu.list"}`, fields `id/label/path/shortcut/enabled/checked`) are NOT
  in `engine.commands` but still run through `engine.execute` (control.rs falls through to
  `menus::invoke` for non-engine ids).

Errors come back as `{"id", "ok": false, "error": "<text>"}`. Failure texts observed live:

| you sent | error text |
|---|---|
| `command` is a stringified envelope | ``unknown command `{"command": "image.adjustments.desaturate"}` `` |
| unknown bare id | ``unknown command `image.adjustments.nope` `` |
| `command` is a JSON object / missing | ``missing `command` `` |

---

## Verified top use cases (photocraft)

All ids below are confirmed present in the live registry with the params verbatim from it.
`…` in the label = dialog in the UI; via `engine.execute` it runs headlessly with defaults.

| want | id | label | params (verbatim from registry) | dialog? |
|---|---|---|---|---|
| Rotate canvas 90° CW | `image.imageRotation.90cw` | 90° Clockwise | `{}` | no |
| Rotate canvas 90° CCW | `image.imageRotation.90ccw` | 90° Counter Clockwise | `{}` | no |
| Rotate canvas 180° | `image.imageRotation.180` | 180° | `{}` | no |
| Flip **canvas** H | `image.imageRotation.flipCanvasHorizontal` | Flip Canvas Horizontal | `{}` | no |
| Flip **canvas** V | `image.imageRotation.flipCanvasVertical` | Flip Canvas Vertical | `{}` | no |
| Arbitrary canvas rotate | `image.rotation.arbitrary` | Arbitrary… | `{"angle":-359.99..359.99=0,"direction":"cw|ccw"="cw","interpolation":"bicubic|bilinear|nearest"="bicubic"}` | `…` |
| Rotate **layer** 90/180 | `edit.transform.rotate90Cw` / `edit.transform.rotate90Ccw` / `edit.transform.rotate180` | Rotate 90° Clockwise / … | `{}` | no |
| Flip **layer** H/V | `edit.transform.flipHorizontal` / `edit.transform.flipVertical` | Flip Horizontal / Vertical | `{}` | no |
| Free transform (move/rotate/scale via quad or matrix) | `edit.transform` | Free Transform | `{"layer":id?,"rect":[x0,y0,x1,y1]? (source frame; default = layer content ∩ selection),"quad":[[x,y]×4]? (where the frame's corners go, clockwise from top-left),"matrix":[a,b,c,d,e,f]? (affine alternative),"interpolation":"bicubic|bilinear|nearest"="bicubic","target":"pixels"\|"mask"\|"quickMask"\|{"channel":i}=Channels panel target (an unlinked mask, an alpha channel or the Quick Mask transforms alone; a linked mask moves with its layer)}` | no |
| **Desaturate (quick grayscale look)** | `image.adjustments.desaturate` | Desaturate | `{}` | no |
| **Black & White (channel mixer B&W)** | `image.adjustments.blackWhite` | Black & White… | `{"reds":-200..300=40,"yellows":-200..300=60,"greens":-200..300=40,"cyans":-200..300=60,"blues":-200..300=20,"magentas":-200..300=80,"tint":bool=false,"tintColor":"#rrggbb"}` | `…` |
| B&W as adjustment layer | `layer.newAdjustmentLayer.blackWhite` | Black & White… | same params as above | `…` |
| Grayscale **color mode** | `image.mode.grayscale` | Grayscale | `{"profile":"<builtin id>\|working\|/path/to/profile.icc"=working,"intent":"perceptual\|relative\|saturation\|absolute"="relative","bpc":bool=true}` | no — **refused by desktop automation, see below** |
| Gaussian blur | `filter.blur.gaussianBlur` | Gaussian Blur… | `{"radius":0.1..1000=1}` | `…` (long command → background job) |
| Other blurs | `filter.blur.boxBlur` `{"radius":1..2000=1}` · `filter.blur.motionBlur` `{"angle":-360..360=0,"distance":1..2000=10}` · `filter.blur.radialBlur` `{"amount":1..100=10,"method":"spin|zoom","centerX":0..1=0.5,"centerY":0..1=0.5}` · `filter.blur.surfaceBlur` `{"radius":1..100=5,"threshold":2..255=15}` · `filter.blur.smartBlur` · `filter.blur.lensBlur` · `filter.blur.shapeBlur` · `filter.blur.blur` / `blurMore` / `average` (no params) | | | |
| Brightness/Contrast | `image.adjustments.brightnessContrast` | Brightness/Contrast… | `{"brightness":-150..150=0,"contrast":-50..100=0,"legacy":bool=false}` | `…` |
| Levels | `image.adjustments.levels` | Levels… | `{"inBlack":0..253=0,"gamma":0.01..9.99=1,"inWhite":2..255=255,"outBlack":0..255=0,"outWhite":0..255=255,"red":json,"green":json,"blue":json} (top level = composite; per channel {"inBlack","gamma","inWhite","outBlack","outWhite"} under red/green/blue, gray, cyan/magenta/yellow/black or lightness/a/b)` | `…` |
| Curves | `image.adjustments.curves` | Curves… | `{"points":json,"red":json,"green":json,"blue":json} (curves as [[in,out],…] in 0..255, 2..19 points: points = composite; …)` | `…` |
| Hue/Saturation | `image.adjustments.hueSaturation` | Hue/Saturation… | `{"hue":-180..180=0,"saturation":-100..100=0,"lightness":-100..100=0,"colorize":bool=false,"reds":json,…}` | `…` |
| Image size / resize | `image.imageSize` | Image Size… | `{"width":px,"height":px,"resolution":ppi,"resample":"bicubic|bilinear|nearest|lanczos|preserveDetails|none"="bicubic"}` | `…` |
| Canvas size | `image.canvasSize` | Canvas Size… | `{"width":px,"height":px,"relative":bool=false,"anchor":"topLeft|top|topRight|left|center|right|bottomLeft|bottom|bottomRight"="center","extensionColor":"background|foreground|white|black|transparent|#rrggbb"="background"}` | `…` |

**Black & white / grayscale — the verdict:**

- `image.adjustments.desaturate` — **in the live registry** (enabled, `{}` params, shortcut
  `Cmd+Shift+U`). This is the id that works for "make it grayscale-looking" while staying in RGB.
  The earlier `unknown command` failure was NOT a missing id (see Anomaly log).
- `image.adjustments.blackWhite` — in the live registry; channel-mixer B&W with optional tint.
  Label ends `…` but `engine.execute` runs it headlessly with the documented defaults.
- `image.mode.grayscale` — **listed** in `engine.commands` (its `enabled` reflects engine
  preconditions only), but the **desktop automation refuses every `image.mode.*`** command:
  `crates/automation/src/workspace.rs` (`authorize_desktop_engine_command`, line ~198) returns
  ``automation command `image.mode.grayscale` uses ambient filesystem paths and is disabled; use capability-scoped document methods`` —
  because mode changes can load colour profiles from app preferences (documented in
  `docs/control-protocol.md` §Engine commands). It IS allowed on the headless server.
  **For agents on the live desktop: use `image.adjustments.desaturate` or
  `image.adjustments.blackWhite`/`layer.newAdjustmentLayer.blackWhite`, never `image.mode.*`.**

Note there is no `edit.transform.freeTransform` id — Free Transform is `edit.transform`.
All `image.adjustments.*` ids have non-destructive twins `layer.newAdjustmentLayer.*`
(same params; adjustments are one generated registry family in commands.rs, `ADJ` table).

---

## Layer ops (north star)

| want | id | label | params (verbatim) | dialog? |
|---|---|---|---|---|
| New layer | `layer.new.layer` | Layer… | `{"name":str?}` | `…` (runs with defaults) |
| New group | `layer.new.group` | Group… | `{"name":str?}` | `…` |
| Duplicate layer | `layer.duplicate` | Duplicate Layer… | `{"layer":id?} (no layer: every selected layer)` | `…` |
| Delete layer | `layer.delete` | Delete Layer | `{"layer":id?} (no layer: every selected layer)` | no |
| Move/translate layer | `layer.translate` | Move Layer | `{"layer":id?,"dx":i32,"dy":i32} (no layer: every selected layer; linked layers follow)` | no |
| **Set blend mode / opacity / fill / name / locks** | `layer.setProps` | Layer Properties | `{"layer":id?,"name":str?,"visible":bool?,"opacity":0..1?,"fill":0..1?,"blend":"Multiply|…"?,"clipped":bool?,"locked":bool?,"locks":{"transparency","pixels","position","artboard","all":bool}?,"channels":[bool,…]? (Advanced Blending: which colour channels blend, R G B / C M Y K / L a b)}` | no |
| Rename layer | `layer.renameLayer` | Rename Layer | `{"layer":id?,"name":str}` | no |
| Select layer | `layer.select` | Select Layer | `{"layer":id,"mode":"replace|toggle|range|add"="replace"} (toggle = ⌘-click, range = ⇧-click)` | no |
| Group selected layers | `layer.groupLayers` | Group Layers | `{"layer":id?,"name":str?} (no layer: every selected layer)` | no |
| Ungroup | `layer.ungroupLayers` | Ungroup Layers | `{"layer":id?}` | no (currently `enabled:false` — needs a group selected) |
| Bring forward / back | `layer.arrange.bringForward` / `layer.arrange.sendBackward` | Bring Forward / Send Backward | `{"layer":id?}` | no |
| Bring to front / send to back | `layer.arrange.bringToFront` / `layer.arrange.sendToBack` | Bring to Front / Send to Back | `{"layer":id?}` | no |
| Reorder to arbitrary place | `layer.moveTo` | Reorder Layer | `{"layer":id?,"target":id,"position":"above|below|into"="above"}` | no |
| Merge down / layers / visible / flatten | `layer.mergeDown` `{"layer":id?}` · `layer.mergeLayers` `{}` · `layer.mergeVisible` `{}` · `layer.flattenImage` `{}` | | | no |
| Clipping mask | `layer.createClippingMask` / `layer.releaseClippingMask` | | `{"layer":id?}` | no |
| Hide / show | `layer.hideLayers` / `layer.showLayers` / `layer.showOnly` | | `{"layer":id?}` | no |
| Blending Options (Blend If) | `layer.layerStyle.blendingOptions` | Blending Options… | `{"layer":id?,"blend":"normal|multiply|…"?,"opacity":0..100?,"fillOpacity":0..100?,"blendIf":{"channel":"gray|red|green|blue|cyan|…"|index="gray","thisLayer":[black,white]|[blackLo,blackHi,whiteLo,whiteHi]?,"underlying":[…]?}|[{…},…]|null?} (Blend If values 0..255; split points fade; null resets)` | `…` |

**Blend mode `layer.setProps {"blend": …}` — full accepted enum** (the registry doc abbreviates
it as `"Multiply|…"`; the parser is `blend_from_str` in `crates/engine/src/commands.rs:176`:
case-insensitive, spaces/underscores/hyphens/parens stripped, matched against the label **or**
the Rust variant name). Photoshop menu order (`BlendMode::LAYER_MODES`, groups add `Pass Through`):

```
Pass Through | Normal | Dissolve | Darken | Multiply | Color Burn | Linear Burn |
Darker Color | Lighten | Screen | Color Dodge | Linear Dodge (Add) | Lighter Color |
Overlay | Soft Light | Hard Light | Vivid Light | Linear Light | Pin Light | Hard Mix |
Difference | Exclusion | Subtract | Divide | Hue | Saturation | Color | Luminosity
```

All of these spellings resolve: `"multiply"`, `"Multiply"`, `"color burn"`, `"ColorBurn"`,
`"colorburn"`, `"Linear Dodge (Add)"`, `"lineardodge"`, `"LinearDodge"`, `"pass through"`.
Bad value → ``unknown blend mode `…` ``. Test from the engine suite:
`layer.setProps {"layer": id, "opacity": 0.5, "blend": "Multiply"}`.

**Opacity note:** `layer.setProps` takes `opacity`/`fill` as **0..1** (`0.5` = 50%),
while `layer.layerStyle.blendingOptions` and `edit.fill` use **0..100**.

Related: `edit.fill` (`{"contents":…,"color":"#rrggbb|[r,g,b,a]","mode":"normal|multiply|…","opacity":0..100=100,…}`),
`gradient.fill.create` (`{"from":[x,y],"to":[x,y],"style":"linear|radial|angle|reflected|diamond","mode":"normal|multiply|…","opacity":0..100=100,…}` → `{"layer":id}`),
`layer.setAdjustment` (`{"layer":id?, …params of that adjustment kind}`) for editing
adjustment layers after creation.

### Common parameter values (spelled exactly)

| param | values |
|---|---|
| `direction` (`image.rotation.arbitrary`) | `"cw"` \| `"ccw"` (default `"cw"`) |
| `interpolation` (transform) | `"bicubic"` \| `"bilinear"` \| `"nearest"` (default `"bicubic"`) |
| `resample` (`image.imageSize`) | `"bicubic"` \| `"bilinear"` \| `"nearest"` \| `"lanczos"` \| `"preserveDetails"` \| `"none"` |
| `anchor` (`image.canvasSize`) | `"topLeft"` `"top"` `"topRight"` `"left"` `"center"` `"right"` `"bottomLeft"` `"bottom"` `"bottomRight"` |
| `blend` / `mode` | the 28 blend names listed above |
| `layer.select` `mode` | `"replace"` \| `"toggle"` \| `"range"` \| `"add"` |
| `layer.moveTo` `position` | `"above"` \| `"below"` \| `"into"` |
| `select.rect` `mode` | `"replace"` \| `"add"` \| `"subtract"` \| `"intersect"` |
| `filter.blur.radialBlur` `method` | `"spin"` \| `"zoom"` |
| `edit.fill` `contents` | `"foreground"` \| `"background"` \| `"color"` \| `"contentAware"` \| `"pattern"` \| `"history"` \| `"black"` \| `"gray"` \| `"white"` |
| colors | `"#rrggbb"` (also `[r,g,b,a]` in some commands), `"foreground"`, `"background"` |

---

## Categories (818 commands)

Search the full registry with `command_list`/`engine.commands` (remember: desktop returns
everything; filter client-side on `id`/`label`). Example ids per category:

| prefix | count | examples |
|---|---|---|
| `layer.*` | 198 | `layer.duplicate`, `layer.setProps`, `layer.translate`, `layer.mergeDown`, `layer.layerMask.revealAll` |
| `filter.*` | 123 | `filter.blur.gaussianBlur`, `filter.noise.addNoise`, `filter.sharpen.unsharpMask`, `filter.render.clouds`, `filter.gallery.*` (~50 artistic filters) |
| `edit.*` | 77 | `edit.transform`, `edit.fill`, `edit.undo`, `edit.contentAwareFill`, `edit.puppetWarp` |
| `image.*` | 64 | `image.imageSize`, `image.canvasSize`, `image.adjustments.*`, `image.rotation.arbitrary`, `image.trim` |
| `type.*` | 59 | `type.create`, `type.edit`, `type.setStyle`, `type.warpText`, `type.rasterize` |
| `file.*` | 48 | `file.new`, `file.revert`, `file.export.saveForWebLegacy`, `file.automate.photomerge` (file open/save via `app.open`/`app.save` methods only — `file.open`/`file.save` are refused) |
| `select.*` | 34 | `select.rect`, `select.magicWand`, `select.subject`, `select.colorRange`, `select.modify.feather` |
| `view.*` | 23 | `view.proofColors`, `view.newGuide`, `view.gamutWarning`, `view.layerMask` |
| `paint.*` | 22 | `paint.gradient`, `paint.bucket`, `paint.cloneStamp`, `paint.stroke` |
| `channel.*` | 21 | `channel.new`, `channel.duplicate`, `channel.split`, `channel.target` |
| `path.*` / `shape.*` | 19 / 9 | `path.set`, `path.fill`, `shape.create`, `shape.edit` |
| `layerComp.*` | 13 | `layerComp.new`, `layerComp.apply`, `layerComp.update` |
| `brush.*` `gradient.*` `pattern.*` `style.*` `tool.*` `tools.*` | 12/11/10/5/5/8 | `brush.presets.list`, `gradient.fill.create`, `pattern.list`, `style.presets.apply`, `tool.presets.select`, `tools.setBrush` |
| `document.*` `jobs.*` `session.*` `command.*` `prefs.*` `plugin.*` `actions.*` | 4/2/1/1/3/5/6 | `document.inspect`, `document.activate`, `jobs.list`, `session.inspect`, `command.list`, `prefs.get`, `actions.play` |
| misc | `cloneSource.*` 5, `count.*` 7, `slice.*` 7, `timeline.*` 7, `notes.*` 4, `measurementLog.*` 3, `variables.*` 1, `color.*` 1 | e.g. `slice.new`, `timeline.setFrame`, `notes.add` |

Selection/transform/inspect ids an agent reaches for constantly:
`document.inspect` (layer tree, history, dims — safe), `document.activate {"document":index}`,
`document.pixel {"x":i32,"y":i32}`, `layer.pickAt {"x":px,"y":px,…}` (auto-select by point),
`session.inspect`, `command.list`.

---

## Gridcraft (lighter survey — source-derived, no running instance)

Same JSON-lines shape. **No auth** (gridcraft-family: one `{"id","method","params"}` line in,
one reply out). Start: `gridcraft --control 7979`. Docs: `~/Downloads/CRAFT/gridcraft-main/docs/control-protocol.md`.
~249 ids extractable from `crates/engine/src/cmd/*.rs` (ids follow the Excel ribbon:
`home.bold`, `insert.chart`, `data.sortAscending`, plus primitives).

**Methods** (control-protocol.md): `engine.execute {command, params}` ·
`engine.commands {search?}` — note the param is **`search`**, not `filter`, and it DOES filter
(id/label/ribbon-path substring) · `engine.journal` · `document.inspect` ·
`sheet.read {range?, sheet?, formulas?, formatted?}` · `cell.get {cell?, sheet?}` ·
`ui.inspect` / `ui.click` / `ui.key` / `ui.text` / `ui.cell.click` / `ui.edit.*` /
`ui.ribbon` / `ui.dialog*` / `ui.screenshot` / `ui.set` / `ui.resize` / `ui.focus` ·
`app.open` / `app.save` / `app.quit`. Any method name that is a command id also runs it.

**Verified ids + params** (verbatim from source `cmd!` registrations):

| id | label | params |
|---|---|---|
| `cell.set` | Enter Cell | `{cell?: "B2", input: "text, number or =formula", sheet?, array?: bool}` — `input` (alias `value`) is required; `{"cell":"B2","input":"=SUM(A1:A9)"}` is the canonical example |
| `cell.get` | Get Cell | `{cell?, sheet?}` → value, formula, display text, style, comment, link |
| `sheet.read` | Read Range | `{range?: "A1:D10" (default: used range), sheet?, formulas?: bool, formatted?: bool}` → rows of values |
| `selection.set` | Select | `{range: "A1:B2,D4" \| cell, active?: "A1", sheet?}` |
| `home.bold` | Bold | `{range?, on?: bool}` (toggle without `on`) |
| `view.theme` | Display Theme | `{mode: "system"\|"light"\|"dark"}` |
| `view.animations` | Animations | `{on?: bool}` (toggles without it) → `{on}` |
| `view.darkMode` | Dark Mode | legacy fixed Light/Dark toggle |
| `app.language.set` | Interface Language | `{language: "en"\|"zh"\|"ja"\|"ko"\|"ru"\|"pt"\|"de"\|"cs"} (alias: code)` |

Command entry fields (gridcraft `CommandInfo`): `id, label, menu, shortcut, params, enabled`,
plus `disabled_reason` when disabled.

**pdfcraft:** the hand-off note "no TCP control channel, file-based only" is **out of date for
the current source** (see Anomaly log): `pdfcraft --control <file>` serves JSON-lines over a
loopback TCP port and writes `{"port","token","pid"}` into `<file>`; the first frame must be
`{"method":"auth","params":{"token":…}}` (JSON-RPC-ish error codes, `crates/ui-egui/src/control.rs`).
The port is random (auth token too), so it cannot be dialed from CLI args alone — read the
control file. `pdfcraft-cli ui --control <file> <method> …` is the intended driver.
Its `ui.state`/`ui.open` surface (annotation editing, text selection, pages_on_screen) is
separate from an `engine.execute` command registry.

---

## Anomaly log

1. **`image.adjustments.desaturate` — id EXISTS in the live registry** (entry captured in
   `live-command-registry.json`; enabled, label `Desaturate`, shortcut `Cmd+Shift+U`,
   params `{}`). The failed call was not a missing command.

2. **The `unknown command {"command": "image.adjustments.desaturate"}` anomaly — root cause
   proven: the envelope was stringified into the `command` field.** The engine's error format
   is ``unknown command `<id>` `` (backticks — `crates/engine/src/lib.rs:112` `UnknownCommand`),
   so the braces you saw are the *contents of the id string*: `command` received the literal
   text `{"command": "image.adjustments.desaturate"}` instead of the bare id.
   **Live reproduction (bogus ids only, nothing mutated):**

   | request `params` | reply `error` |
   |---|---|
   | `{"command": "{\"command\": \"image.adjustments.desaturate\"}", "params": {}}` | ``unknown command `{"command": "image.adjustments.desaturate"}` `` ← exact reported text |
   | `{"command": {"command": "document.inspect"}, "params": {}}` | ``missing `command` `` (must be a string) |
   | `{"params": {}}` | ``missing `command` `` |
   | `{"command": "image.adjustments.nope", "params": {}}` | ``unknown command `image.adjustments.nope` `` (clean missing-id form) |

   Parsing evidence: `crates/automation/src/rpc.rs:68-71` does
   `str_of(&p, "command")` → non-strings fail with `engine.execute needs \`command\``;
   `crates/ui-egui/src/control.rs:167-183` does `s("command").or(s("id"))` then
   `commands::find(id)` — a stringified envelope simply misses the lookup and falls to
   `UnknownCommand`. So the **request envelope was wrong, the id was right.** Where the
   stringification happened upstream (controller `command_run` arg parsing vs. the LLM tool
   call emitting `command: "{\"command\": …}"`) is outside the app; the app behavior is now
   pinned down.

   **Correct envelope + WORKING read-only test (ran live, `ok:true`):**
   ```json
   {"id": 3, "method": "engine.execute", "params": {"command": "document.inspect", "params": {}}}
   ```
   (`params` object may be omitted entirely.) The known-good mutating example from previous
   sessions is `{"command": "image.imageRotation.90cw", "params": {}}` — not re-run here.

3. **Source ↔ live registry diff** (static `cmd!`/`spec!`/`key_cmd!`/`CommandSpec` extraction,
   656 ids, vs 818 live): the gap is generated registrations — the `ADJ` table produces
   `image.adjustments.*` + `layer.newAdjustmentLayer.*` pairs (commands.rs:912+),
   `gallery_cmds` produces `filter.gallery.*`, `prefs_ui` produces `edit.preferences.*`.
   Only genuine source-side id absent from the engine registry: **`file.clearRecent`** —
   it is a UI-menu id (menus.rs:243) handled by `menus::invoke`, not an engine command.
   Conversely `colorOverlay`/`satin` short keys are layer-style param tokens, not ids.
   `image.adjustments.desaturate` is in **both** (commands.rs:775 and live). No other
   source/live divergence found among the surveyed ids.

4. **Desktop `engine.commands` ignores `filter`** (verified live — every filter returns 818
   entries; control.rs:183 calls `command.list` with `json!({})`). The headless server filters.
   Consequence for our controller: `command_list {filter}` against the live desktop returns the
   whole registry and must be filtered in `controller/live.py` (today it is not).

5. **`edit.transform.freeTransform` does not exist** — Free Transform's id is `edit.transform`.

6. **pdfcraft control channel:** the team note says "file-based control — no TCP port". The
   current pdfcraft source (`apps/pdfcraft/src/main.rs`, `crates/ui-egui/src/control.rs:649+`)
   binds `127.0.0.1:<random>` TCP and publishes `{"port","token","pid"}` via the `--control`
   file. It is TCP underneath; the *endpoint* is file-discovered. Update the attach hints in
   `controller/live.py` when someone picks pdfcraft up.

7. **`image.mode.*` asymmetry:** present + `enabled:true` in `engine.commands`, but refused by
   desktop automation authorization (`workspace.rs`) while allowed headless. `enabled:true`
   means "engine preconditions pass", not "automation will run it" — treat `enabled` as a hint,
   the authorization layer is the last word for `image.mode.*`, `file.*` (except `file.new`,
   `file.close*`, `file.fileInfo`) and path-param commands (`layer.exportAs {path}` etc.,
   error: ``automation command `…` uses ambient filesystem paths and is disabled; use capability-scoped document methods``).
