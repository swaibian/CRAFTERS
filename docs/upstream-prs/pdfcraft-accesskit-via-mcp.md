# Upstream PR draft: pdfcraft — AccessKit tree via MCP

**Target repo**: `storytold/pdfcraft` (path: `pdfcraft-main/` in local checkout)
**Type**: Minimal upstream contribution (reference for SW-REQ-A11Y)
**Status**: 📝 Draft — apply against the local checkout, test, then submit upstream

---

## Problem

pdfcraft already computes the most capable perception surface in the fleet
(`crates/ui-egui/src/control.rs`): every frame, `output_hook` caches
`platform_output.accesskit_update` into `Shared { nodes, root, focus }`,
and `Control::inspect` walks the tree emitting
`{widgets: [{id, role, depth, enabled, clickable, focusable, label, value,
description, rect, toggled, selected, focused}], count, truncated}` with
`{query?, role?, limit?}` filters (default 500).

But it is reachable **only** over the control channel
(`pdfcraft-cli ui --control FILE ui.inspect …`). The MCP server
(`apps/pdfcraft-cli/src/main.rs::mcp()`) is headless-only and never offers
it — so the richest widget tree in the org is invisible to MCP agents.

## Change (2 files, ~60 lines)

### 1. `apps/pdfcraft-cli/src/main.rs` — register the tool

In the MCP tool table (next to `doc_inspect`), add `ui_inspect` as a
**bridge-conditional** tool (CADCraft pattern — never advertise a tool that
will fail headless):

```rust
// Bridge-only: offered iff a control channel is attached.
if control.is_some() {
    tools.push(ui_inspect_tool());
}
```

`ui_inspect {query?, role?, limit?}` → forwards to
`Control::inspect` and returns its `{widgets, count, truncated}` verbatim.
No new serialization: the `widget()` shape is already JSON-safe
(string ids — 64-bit ids don't survive double-based parsers).

### 2. `crates/ui-egui/src/control.rs` — expose `focused` filter

`inspect()` currently filters on `{query, role, limit}`. Add the
`focused: bool` filter the gateway contract expects (one `if` + param
read, mirroring `role`):

```rust
let focused = p.get("focused").and_then(Value::as_bool);
// ... in the walk:
let focused_ok = focused.is_none_or(|f| /* node is s.focus */ == f);
```

The focus node is already tracked (`s.focus`); this only surfaces it.

## Test plan (upstream `cargo test`)

- `ui.inspect` with no app window → tool absent from `tools/list`
  (headless contract preserved).
- `ui.inspect` bridged → returns `{widgets, count, truncated}`; `query`
  narrows; `role` narrows; `limit: 1` truncates.
- Clicks still drive widgets via `accesskit::ActionRequest` (unchanged
  path — `ui.click {id}` / `{label}`).

## Gateway fallback (works with or without this PR)

`gateway/perception.py::craft_widgets` proxies `ui.widgets` /
`ui_widgets` / `accesskit_tree` when a backend offers them and falls back
to the canned AccessKit-contract shape otherwise. The gateway works today;
this PR removes the shim for pdfcraft.
