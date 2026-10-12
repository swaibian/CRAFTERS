# 05 — Quickstart

Working configurations you can copy today. Nothing here requires writing a line of code.

---

## 1. Where the binaries are

| Platform | Desktop app | CLI |
|---|---|---|
| Linux (deb/rpm) | `/usr/bin/<app>` | `/usr/bin/<app>-cli` |
| Windows (MSI, default) | `C:\Program Files\<App>\<app>.exe` | `C:\Program Files\<App>\<app>-cli.exe` — **not on `PATH`** |
| macOS | `/Applications/<App>.app` | separate `<app>-cli-<version>-macos-<arch>.zip` release asset; the `.app` bundle holds only the GUI |

Confirm with: `<app>-cli --version`.

---

## 2. Layer 0 — register the MCP servers directly

### Claude Code (project scope, `.mcp.json`)

```json
{
  "mcpServers": {
    "photocraft": {
      "command": "/usr/local/bin/photocraft-cli",
      "args": ["mcp", "--automation-read-root", "/work/project",
               "--automation-write-root", "/work/project"]
    },
    "pdfcraft": {
      "command": "/usr/local/bin/pdfcraft-cli",
      "args": ["mcp", "--root", "/work/project"]
    },
    "gridcraft": { "command": "/usr/local/bin/gridcraft-cli", "args": ["mcp"] },
    "soundcraft": { "command": "/usr/local/bin/soundcraft-cli", "args": ["mcp"] },
    "cadcraft":  { "command": "/usr/local/bin/cadcraft-cli",  "args": ["mcp"] },
    "deckcraft": { "command": "/usr/local/bin/deckcraft-cli", "args": ["mcp"] },
    "designcraft": { "command": "/usr/local/bin/designcraft-cli", "args": ["mcp"] },
    "lightcraft": { "command": "/usr/local/bin/lightcraft-cli", "args": ["mcp"] },
    "vectorcraft": {
      "command": "/usr/local/bin/vectorcraft-cli",
      "args": ["mcp", "--headless", "--automation-read-root", "/work/project",
               "--automation-write-root", "/work/project"]
    },
    "effectcraft": { "command": "/usr/local/bin/effectcraft-cli", "args": ["mcp"] },
    "filmcraft":  { "command": "/usr/local/bin/filmcraft-cli",  "args": ["mcp"] },
    "wordcraft": {
      "command": "/usr/local/bin/wordcraft-cli",
      "args": ["mcp", "--author", "Agent (automated edits)"]
    }
  }
}
```

From the shell:

```sh
claude mcp add photocraft  -- /usr/local/bin/photocraft-cli mcp \
  --automation-read-root /work/project --automation-write-root /work/project
claude mcp add gridcraft  -- /usr/local/bin/gridcraft-cli mcp
claude mcp add soundcraft -- /usr/local/bin/soundcraft-cli mcp
```

### Claude Desktop / Cursor / any JSON-config client

Same `command` + `args`. Use **absolute paths**.

### ⚠️ Start with two, not twelve

~270 tool definitions will overwhelm most clients, and several apps share tool names
(`execute`, `list_commands`, `click`, `key`, `batch`, `screenshot`). Start with:

```json
{ "mcpServers": {
    "gridcraft": { "command": "/usr/local/bin/gridcraft-cli", "args": ["mcp"] },
    "photocraft": { "command": "/usr/local/bin/photocraft-cli", "args": ["mcp",
      "--automation-read-root", "/work/project", "--automation-write-root", "/work/project"] }
} }
```

If that works well, add `pdfcraft` and `vectorcraft`, then the rest. Build the gateway
(`02-ARCHITECTURE.md`) when the tool count bites.

---

## 3. Per-app CLI reference

### Headless MCP (default — no window, no GPU, instant)

```sh
photocraft-cli   mcp --automation-read-root DIR --automation-write-root DIR
pdfcraft-cli     mcp [--root DIR] [--compact]
filmcraft-cli    mcp [--demo | --project FILE | --data-dir DIR]
vectorcraft-cli  mcp [--headless | --in FILE] [--automation-read-root DIR] [--automation-write-root DIR]
lightcraft-cli   mcp [--headless | --demo | --library] [--compact]
designcraft-cli  mcp [--in FILE | --sample]
effectcraft-cli  mcp [--demo | --project FILE] [--gpu] [--autosave] \
                         [--automation-read-root DIR] [--automation-write-root DIR]
gridcraft-cli    mcp [--in FILE | --sample NAME]
cadcraft-cli     mcp [--sample NAME]
deckcraft-cli    mcp [--in FILE | --sample]
soundcraft-cli   mcp [--demo | --in FILE | --sample]
wordcraft-cli    mcp [--author NAME]
```

`--compact` exists only on **pdfcraft** and **lightcraft** — they cut the tool list to the 5-tool
core plus `tool_search`/`tool_call`. Use these first if tool count is a problem.

### Bridge mode — drive the live GUI

Start the app with a control port, then point the CLI at it.

```sh
# 1. start the desktop app with the control channel open
photocraft   --control 7878 --control-token-file ~/.photocraft-control.token \
             --automation-read-root /work/project --automation-write-root /work/project &
vectorcraft  --control 7979 &
lightcraft   --control 7980 &
designcraft  --control 7979 &
gridcraft    --control 7979 &
cadcraft     --control 7979 &
deckcraft    --control 7990 &
soundcraft   --control 7801 &
wordcraft    --control 7981 &
filmcraft    --control 9876 &
effectcraft  --control 9877 &
# pdfcraft: a control FILE, not a port
pdfcraft     --control ~/.pdfcraft-control.json &

# 2. bridge the MCP server to it
photocraft-cli  mcp --bridge 127.0.0.1:7878 --control-token-file ~/.photocraft-control.token
filmcraft-cli   mcp --bridge 127.0.0.1:9876
effectcraft-cli mcp --bridge 9877
vectorcraft-cli mcp --connect 127.0.0.1:7979
lightcraft-cli  mcp --connect 127.0.0.1:7980
designcraft-cli mcp --connect 7979
gridcraft-cli   mcp --connect 7979
cadcraft-cli    mcp --connect 7979
deckcraft-cli   mcp --connect 7990
soundcraft-cli  mcp --connect 7801
wordcraft-cli   mcp --connect 127.0.0.1:7981
# pdfcraft has no bridge mode — use `pdfcraft-cli ui --control FILE <method> [k=v ...]`
```

Bridge adds the live-window tools: `screenshot`, `ui_inspect`, `ui_pointer`, `ui_click`, `ui_key`,
`ui_type`, `ui_set`, `ui_menu_invoke` / `menu_invoke`, and `control_call` / `call_app`.

`cadcraft` is **fail-closed**: without `--connect` it errors rather than silently falling back to
headless, so an agent aimed at the app can never quietly edit a separate drawing.

---

## 4. Non-MCP batch scripting (fastest for pipelines)

Bypass MCP framing entirely. Often 2–5× faster for bulk work.

```sh
# PhotoCraft — JSON-lines server on stdio, no MCP framing, no per-command startup
printf '%s\n' \
  '{"id":1,"method":"doc.open","params":{"path":"in.jpg"}}' \
  '{"id":2,"method":"batch","params":{"steps":[
      {"command":"image.adjustments.invert"},
      {"command":"filter.blur.gaussianBlur","params":{"radius":3}}]}}' \
  '{"id":3,"method":"doc.save","params":{"path":"out.png"}}' \
| photocraft-cli serve --automation-read-root /work/project --automation-write-root /work/project
```

`serve` also takes `--port N` to listen on loopback TCP.

```sh
# PdfCraft — JSON array of {"tool": …, "args": {…}}
pdfcraft-cli run --script steps.json --root /work/project

# DesignCraft — one command per line; "$N.path" pulls a value from step N
cat > page.dcs <<'DCS'
frame.create {"rect": [72, 72, 540, 300], "content": "text", "text": "Results of the survey"}
text.select  {"story": "$0.story", "anchor": 0, "focus": 0}
DCS
designcraft-cli script page.dcs
```

Discovering commands without an agent:

```sh
photocraft-cli   commands | jq .
designcraft-cli  commands footnote        # filter
designcraft-cli  describe xref.insert     # label, menu path, shortcut, params
gridcraft-cli    commands
gridcraft-cli    functions               # formula function catalogue
soundcraft-cli   describe <command-id>
effectcraft-cli  schemas
```

---

## 5. Cloud API (ArtCraft hosted)

```sh
export ARTCRAFT_API_KEY=artcraft_api_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
export ARTCRAFT_API=https://api.storyteller.ai

# Discovery — both public, no auth needed
curl -s "$ARTCRAFT_API/v1/omni_gen/models/image" | jq '.models[].id'
curl -s "$ARTCRAFT_API/v1/omni_gen/cost/image" -H 'content-type: application/json' \
  -d '{"model":"Seedream4","prompt":"a red fox in snow"}' | jq .

# Generate
TOK=$(curl -s -X POST "$ARTCRAFT_API/v1/omni_api/generate/image" \
  -H "Authorization: Bearer $ARTCRAFT_API_KEY" -H 'content-type: application/json' \
  -d "{\"idempotency_token\":\"$(uuidgen | tr 'A-Z' 'a-z')\",\"model\":\"Seedream4\",\"prompt\":\"a red fox in snow\"}" \
  | jq -r .inference_job_token)

# Poll
curl -s "$ARTCRAFT_API/v1/omni_api/job_status/job/$TOK" -H "Authorization: Bearer $ARTCRAFT_API_KEY" \
  | jq '.state.maybe_result.media_links.cdn_url'
```

> **Never** put `ARTCRAFT_API_KEY` in an MCP config or a tool-call argument. Gateway config only.
> Details and gotchas in `03-ARTCRAFT-CLOUD-API.md`.

---

## 6. A good first agent session

```
You have a spreadsheet MCP (gridcraft). Open /work/project/budget.xlsx, add a
"Forecast" sheet with 12 months of projections, put the sum in B14 and a SUMIF
by category in B15, then chart it. Save in place.
```

```
You have a spreadsheet MCP and a PDF MCP. Read /work/project/q3.pdf, build a
summary table in /work/project/q3-summary.xlsx, and export it back to
/work/project/q3-summary.pdf.
```

```
You have a vector MCP. Design a logo: a wordmark reading "Northwind" with a
compass-rose mark, three colour variants, saved as /work/project/logo.svg.
```

These all work today against the existing per-app servers. No wrapper required.

---

## 7. What to do next

| Situation | Do this |
|---|---|
| It works, tool count is fine | Nothing. Use Layer 0. |
| The agent picks the wrong app's `execute` | Prefix tool names per app, or move to the gateway. |
| Context is being crowded | Use `pdfcraft --compact` and `lightcraft --compact`. Drop to 3–4 servers. |
| You want one integration to maintain | Build the gateway — `02-ARCHITECTURE.md` §3. |
| You're running untrusted agents | Containerise. `04-SECURITY.md` §3. |
| You want this upstream | Extract the shared MCP shell to `craft-libs` — `02-ARCHITECTURE.md` §4. |