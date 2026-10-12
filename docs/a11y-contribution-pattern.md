# Accessibility Contribution Pattern

**Status**: ✅ Reference pattern (from TC-C-01's two refs)
**Goal**: Any of the remaining 10 Craft apps reaches 100% agent-accessibility
with one small upstream PR each — no new design work per app.

---

## 1. The pattern (2 PR shapes)

Every app needs exactly the two channels the refs proved. Pick the shape
that matches what the app already computes:

### Shape W — Widget tree via MCP (pdfcraft ref)

**Applies when**: the app caches an accessibility/widget tree per frame but
exposes it only over the control channel (pdfcraft: `Shared { nodes, root,
focus }` in `crates/ui-egui/src/control.rs`, `inspect()` walker).

**PR contents** (pdfcraft: ~60 lines, 2 files):

1. Register the existing walker as a **bridge-conditional** MCP tool —
   offered iff a control channel is attached (CADCraft `has_ui` pattern:
   never advertise a tool that will fail headless).
2. Filter params mirror the walker: `{query?, role?, focused?, limit?=500}`.
3. Wire widget actions (click/focus by id) through the existing action path
   (`accesskit::ActionRequest`), not pointer synthesis.
4. Tests: tool absent headless; present bridged; query/role/limit narrow;
   string ids (64-bit ids don't survive double-based JSON parsers).

Full draft: `docs/upstream-prs/pdfcraft-accesskit-via-mcp.md`.

### Shape M — Canvas-rect mapping (photocraft ref)

**Applies when**: pointer input and click input live in different coordinate
spaces and the view reports zoom/centre but no canvas rect (photocraft:
`ui.pointer` = document px, `ui.click` = screen points, `views[]` without
rect).

**PR contents** (photocraft: ~40 lines, 1 file):

1. Add `canvasRect {x, y, w, h}` to the existing view serialization —
   one field, no new tools/methods.
2. Contract: `screen = (doc - centre) * zoom + view_size / 2`;
   `canvasRect` = document origin/extent through that mapping, in logical
   points (egui convention, not device pixels).
3. Tests: `w/h > 0`; `doc_to_screen(origin) == (x, y)`; zoom doubles `w/h`;
   pan moves `x/y`.

Full draft: `docs/upstream-prs/photocraft-canvasrect.md`.

### Gateway side (both shapes)

`gateway/perception.py` already speaks both contracts:

- `craft_widgets(app, query?, role?, focused?, limit?)` proxies
  `ui.widgets` / `ui_widgets` / `accesskit_tree` when offered, canned
  AccessKit-contract shape otherwise.
- `craft_map(app, direction, …)` synthesizes the mapping from
  caller-supplied view state until the upstream rect is authoritative.
- `query_map` stores resolved mappings per session.

A PR landing only **removes the shim** for that app — nothing else changes.

---

## 2. Decision tree (which shape for app X?)

```
Does the app cache a per-frame widget/a11y tree?
├─ YES, control-channel only → Shape W (expose the walker via MCP)
├─ NO, but ui-egui with accesskit feature on → Shape W-lite:
│   cache platform_output.accesskit_update per frame (copy pdfcraft's
│   output_hook, ~15 lines), then Shape W
└─ NO tree at all → skip W; check coordinates:
    Do pointer and click live in different spaces?
    ├─ YES and no canvas rect → Shape M (add the rect field)
    └─ NO (canvasRect + view already, e.g. vectorcraft/cadcraft/deckcraft)
        → nothing needed; verify with craft_map
```

---

## 3. Third-app scoping exercise: gridcraft (no new design)

Gridcraft (`gridcraft-main/` local checkout) scoped in ~10 minutes against
its sources — proof the pattern generalizes:

- **Coordinates**: `ui.inspect` reports `"grid": cells_rect [l, t, w, h]` +
  `"scroll": [x, y]` (`crates/ui-egui/src/control.rs:80-81`) — a grid rect
  already exists, so **no Shape M needed**. Cell addressing is A1
  references (`ui.cell.click {cell}`), which sidestep pixels entirely.
- **Widgets**: `ui.inspect` covers ribbon/editor/dialog/grid geometry but
  there is no per-frame widget walker with ids — **Shape W-lite applies**:
  cache `accesskit_update` per frame (the `accesskit` feature is already
  enabled in gridcraft's desktop/web binaries per spec §1.6), expose as a
  bridge-conditional MCP tool with the same `{query?, role?, focused?,
  limit?}` contract.
- **Structure**: `inspect_workbook` (sheets/ranges/formulas) already covers
  Tier-1 perception via `crates/mcp/src/tools.rs` — nothing needed.
- **Known gap (out of scope)**: headless gridcraft has no sheet raster
  (spec Tier-2 gap) — a renderer PR, not an accessibility PR.

**Estimated PR**: ~80 lines (15-line frame hook + 60-line tool
registration + tests). No design questions open.

---

## 4. Review checklist (per-app PR)

- [ ] Bridge-conditional: tool absent headless, present bridged (CADCraft rule)
- [ ] String ids everywhere (no raw 64-bit through JSON)
- [ ] Filter contract matches: `{query?, role?, focused?, limit?=500}`
- [ ] No PII in new log lines (widget text never logged verbatim)
- [ ] Gateway shim verified redundant for this app (`craft_widgets` hits live)
- [ ] `cargo test` green in the app repo; gateway suite green here
- [ ] This doc's §2 tree updated if the app needed a new branch

---

## 5. Rollout backlog (deferred, in priority order)

| App | Shape | Notes |
|-----|-------|-------|
| gridcraft | W-lite | Scoped above (§3) |
| lightcraft | verify | Has `list_widgets` already; check filter parity |
| filmcraft / effectcraft | verify | Have `ui_elements`; check filter parity |
| vectorcraft, cadcraft, deckcraft, wordcraft, designcraft | verify/skip | Coordinate mapping already exposed; confirm via `craft_map` |
| soundcraft | W-lite | Thinnest UI state; timeline rects only |

Rollout is explicitly out of scope for EPIC_001 (brief §2) — this table is
the starting point when it is scheduled.
