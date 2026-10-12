# Upstream PR draft: photocraft — canvasRect synthesis

**Target repo**: `storytold/photocraft` (path: `photocraft-main/` in local checkout)
**Type**: Minimal upstream contribution (reference for SW-REQ-A11Y)
**Status**: 📝 Draft — apply against the local checkout, test, then submit upstream

---

## Problem

photocraft's pointer model is split-brained (spec §1.8):

- `ui.pointer` takes **document pixels** (pen simulation).
- `ui.click` / `ui.move` take **screen points**.
- `views[]` (per-window `ui.inspect`) reports zoom/centre/rotation — but
  **no canvas rect**.

So an agent that reads `views[]` cannot convert a document coordinate to
the screen point to click, nor crop a window screenshot to the canvas
(spec §2.1.1). Every other raster app exposes `canvasRect` + view;
photocraft is the outlier.

## Change (1 file, ~40 lines)

### `crates/ui-egui/src/` — report `canvasRect` in `views[]`

Wherever a view entry is serialized for `ui.inspect` (same site that
writes `zoom`/`centre`/`rotation`), add the canvas rect derived from the
already-known view state:

```rust
// view: { zoom: f32, centre: Pos2 /* doc px */, .. }
// canvas: document size in px; view: viewport size in points.
let origin = view_origin_in_screen_points(view, canvas);
view_json["canvasRect"] = json!({
    "x": origin.x, "y": origin.y,
    "w": canvas.w * view.zoom, "h": canvas.h * view.zoom,
});
```

Contract (matches `gateway/perception.py::synthesize_canvas_rect`):

- `screen = (doc - centre) * zoom + view_size / 2`
- `canvasRect = {x, y, w, h}` with `(x, y)` = screen position of document
  origin `(0, 0)`, `w/h` = canvas size scaled by zoom.
- Logical points, not device pixels (egui convention).

No new tools, no new methods — one field on an existing structure, so all
existing consumers keep working.

## Test plan (upstream `cargo test`)

- `ui.inspect` view entries carry `canvasRect` with `w/h > 0`.
- `doc_to_screen(origin) == (canvasRect.x, canvasRect.y)` (round-trip
  against the gateway math).
- Zoom 2× doubles `w/h`; panning moves `x/y` (centre coupling).

## Gateway fallback (works with or without this PR)

`gateway/perception.py::craft_map` implements the same math
(`doc_to_screen` / `screen_to_doc` / `synthesize_canvas_rect`) from
caller-supplied view state, with `query_map` backing per session. The
gateway works today; this PR makes the rect authoritative instead of
synthesized.
