# PhotoCraft operating skill

You edit a layered image in the user's live desktop document. Use these recipes
directly when their command IDs exist in the connected registry; discovery is for
unfamiliar capabilities, not a mandatory step before each known operation.

## Targets and scope
- Inspect initial state: layer IDs, activeLayer, selectedLayers, bounds and selection.
- Resolve “that copy” / “new layer” from prior edits and current IDs. Never invent IDs.
- `layer.select {"layer": ID}` makes a specific layer active before active-layer adjustments.
- A document color-mode conversion affects the entire document; a pixel adjustment
  affects the active editing target; an adjustment layer is a separate non-destructive layer.
- Opacity and fill in `layer.setProps` are fractions 0..1, not percentages.
- Selection coordinates are document pixels, not screen/window pixels.

## Common recipes
- Duplicate: `layer.duplicate {"layer": ID}`. Capture returned IDs and inspect the
  new stack. Preserve the new ID for subsequent “the duplicated layer” requests.
- Make a raster layer black and white: select its ID, then
  `image.adjustments.desaturate {}` (quick grayscale) or
  `image.adjustments.blackWhite {}` (channel-mixed B&W with defaults).
  Do not use `image.mode.grayscale` for a single-layer request.
- Non-destructive B&W when requested: `layer.newAdjustmentLayer.blackWhite {}`;
  inspect scope/clipping so it affects the intended layer.
- Set blend: `layer.setProps {"layer": ID, "blend": "Screen"}`. Other accepted
  modes include Normal, Multiply, Overlay, Darken, Lighten, Soft Light, Hard Light,
  Color Dodge, Color Burn, Difference and Exclusion. Modes are parameter values,
  not separate command IDs. Verify the target layer's `blend` value afterward.
- Set opacity: `layer.setProps {"layer": ID, "opacity": 0.5}` for 50%.
- Circle/ellipse selection: `select.rect {"x": X, "y": Y, "width": W,
  "height": H, "ellipse": true, "mode": "replace"}`. Equal W/H makes a circle.
  The command label says Rectangular Selection but its ellipse flag creates an ellipse.
- Select around visible people/objects: call `look`, locate the intended subjects
  in the actual image, map to document coordinates, then execute the selection.
  If the image/coordinate mapping is insufficient, ask a targeted question;
  repeating look without new information will not resolve the target.
- Canvas rotation: `image.imageRotation.90cw {}`; layer rotation instead uses
  `edit.transform.rotate90Cw`. Use the requested scope.

## Verification and discovery
Inspect the exact target after an edit. Selection verification uses hasSelection
and selectionBounds; blend verification uses the layer ID and blend. Pixel-based
adjustments need visual/pixel evidence, not merely a changed history count.
For unfamiliar operations use a focused command_list keyword, then command_describe
for full parameters. Respect enabled state and explain unavailable capabilities.
Save only when explicitly requested. Finish with done describing achieved edits
and any unresolved part; never claim an edit based on discovery calls alone.
