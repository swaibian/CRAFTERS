# 07 — Agentic Teams for the Craft Suite (Scaico)

Companion to `06-PERCEPTION-AND-INTEGRATION.md`.

**Reference schema:** `example/timeattack_vehicle_dynamics_2026-10-11T18-10-42.json`
**Generated teams:** `teams/craft_studio_2026-10-11.json`, `teams/craft_motion_2026-10-11.json`,
`teams/craft_documents_2026-10-11.json`
**Generator:** `build_teams.py` · **Validator:** `validate_teams.py`

---

## 1. What the Scaico format tells us

Reading the reference team closely, five constraints fall out that shape everything below.

| Observation | Consequence |
|---|---|
| `"transport": "streamable_http"` with a `url` + `token` | **The gateway must be a hosted HTTP MCP server, not stdio.** A hosted team cannot spawn local processes. stdio stays as a secondary transport for local interactive clients. |
| `"tools": ["get_lap_detail", …]` — flat strings | **Tool names must be flat and globally unique.** No `see.window` namespacing, no per-server suffixes. Hence `see_window`, `act_command`, `query_ui`. |
| `"tools"` repeated in `mcp_servers[].tools` | The allowlist is duplicated per server. Keep them identical — a mismatch is a silent config bug. The validator checks this. |
| `skills: []` — present but always empty | The natural home for knowledge. See §5. |
| `instances: 1`, `temperature`, `color`, `dynamic_fields` | Per-agent runtime knobs. `instances` is the parallelism dial. |

Also worth noting from the reference team's own design: the coordinator is explicitly told to
*"INSTANTLY FORWARD SESSION, LAP, ZONE IDS … IN PARALLEL"* and *"Treat missing telemetry streams
as a capability result, not a crash."* The Craft equivalents are **app availability** and
**confinement flags**. Both are addressed in the generated instructions.

---

## 2. The organising principle

> **One application, one agent. Always.**

This is not a stylistic preference. A GUI application has **one selection, one active layer, one
undo stack, one canvas**. Two agents driving the same app concurrently will interleave edits in
ways that are nearly impossible to debug — and no amount of prompt engineering fixes it.

So the gateway must own a **per-app mutex** (`team_claim`), and the team roster is built around
it. The reference team's 7 agents split one domain (vehicle dynamics) into 6 specialties. Here,
the specialisation axis is **the application**, because the application *is* the stateful
resource.

Three tiers follow:

| Tier | Agents | Tool access | Count |
|---|---|---|---|
| **Leader** | 1 per team | `see_*`, `query_*`, `team_*` — **no `act_*`** | 1 |
| **App specialist** | 1 per application | `see_*`, `query_*`, `act_*`, `doc_*`, `job_*`, `team_claim`/`release`/`checkpoint` | 1 each |
| **Read-only** | curator, QA | `see_*`, `query_*`, `team_asset_*` — **no `act_*`** | 2, `instances: 2` |

**The leader never calls `act_*`.** It resolves the brief, routes, and signs off. That guarantees
it cannot corrupt a session, and it means the leader can always be re-run without side effects.

**Read-only agents can span every app.** They cost nothing and can be replicated. That is why
curator and QA get `instances: 2`.

### 2.1 Why `instances` sits on the read-only agents

`instances` multiplies agents that have **no side effects**, so concurrency is free. A specialist
holding an app mutex cannot be multiplied — the second instance would just queue.

But specialists *can* be multiplied per session: each Scaico conversation/session gets its own
headless app instance, so two users working on two budget spreadsheets genuinely do not collide.
Replicas are safe because the mutex is **per app instance**, not per app.

---

## 3. Tool → agent matrix

The gateway exposes a flat `see_*` / `query_*` / `act_*` / `doc_*` / `job_*` / `team_*` vocabulary
plus `cloud_*`. This is how they distribute across the rosters (measured from the generated JSON,
not aspirational):

| Role | studio | motion | documents | Share |
|---|---|---|---|---|
| Leader (`*_lead`) | 32 | 32 | 32 | `see_*`, `query_*`, `team_*` (no `act_*`), `job_wait`, assets |
| App specialist | 53–57 | 53–57 | 53 | full vocabulary + mutex + checkpoint + assets (+ `cloud_*` on the granted few) |
| Read-only (curator, QA) | 29 | 29 | 29 | `see_*`, `query_*`, notify/handoff, assets, `job_wait`, `team_status`, `team_record` |
| **Union per team** | **57** | **57** | **53** | 4 `cloud_*` granted to photo/lightcraft (studio) and film (motion) only |

`film_editor`, `photo_artist` and `lightcraft_artist` carry 57 because that is where the 4 measured
`cloud_*` tools are granted (`cloud_models`, `cloud_cost`, `cloud_generate`, `cloud_job` —
**never** `cloud_upload`/`cloud_download`, and never on leaders or read-only agents).

Per-agent footprint: **29–57 tools**. That larger headroom versus the old 24-tool estimate is
deliberate and still safe: the allowlist is per-agent, so each specialist sees only its slice,
and the full surface stays addressable. Compare to registering all 12 apps directly, which would
put ~270 tools in one context.

### 3.1 The read-only guarantee is enforced, not requested

The validator asserts that every agent whose id ends in `_qa`, `_curator` or `_lead` has **no
tool starting with `act_`**. If someone later adds `act_command` to the QA reviewer, validation
fails. Read-only-ness should be a build-time property, not a prompt instruction.

---

## 4. The three generated teams

### 4.1 `craft_studio` — 11 agents

| Agent | Owns | Notable |
|---|---|---|
| `studio_lead` | — (leader) | Resolves the brief to an asset list, routes by **artifact kind not app name**, checks `team_apps` before routing, parallelises independent work |
| `photo_artist` | photocraft | `see_scopes` for `document.sampleColor` + Camera Raw histograms |
| `lightcraft_artist` | lightcraft | `see_element_state` to find Develop controls by id |
| `vector_artist` | vectorcraft | MCP resources (`vectorcraft://object/{id}`), completion, workflow prompts |
| `layout_artist` | designcraft | `render_page` = printing items only; script format for repetitive layout |
| `deck_builder` | deckcraft | `call_app` exists — flagged as unverified |
| `doc_writer` | wordcraft | Author attribution; `review.trackChanges` needs explicit `{"value": true}` |
| `pdf_specialist` | pdfcraft | `ocr_extract`, `doc_compare{visual:true}`, a11y tools are PDF-tagging not UI |
| `data_analyst` | gridcraft | `write_range` over per-cell; `list_functions` before any formula |
| `asset_curator` | all (read-only) | Provenance authority; `instances: 2` |
| `qa_reviewer` | all (read-only) | Structure → look → scopes → diff → bridge; `instances: 2` |

### 4.2 `craft_motion` — 5 agents

`motion_lead` → `motion_artist` (effectcraft) · `film_editor` (filmcraft) ·
`audio_engineer` (soundcraft) · `motion_qa` (read-only).

The sequencing insight the lead encodes: **sound runs in parallel with the visual pass once the
structure is fixed.** That is the largest wall-clock saving available.

`film_editor` gets `see_scopes` (wrapping `scopes.read` — waveform, parade, histogram,
vectorscopeYuv/Hls, with peaks and traces). Its instruction says plainly: *never judge exposure
or colour from a screenshot.* It also carries the warning that **FilmCraft has no folder
confinement**.

### 4.3 `craft_documents` — 7 agents

`documents_lead` → `pdf_specialist` · `doc_writer` · `data_analyst` · `layout_artist` ·
`cad_drafter` · `documents_qa` (read-only).

The PDF specialist's framing captures the real value of that app in a team: **extract once,
blackboard it, everyone else reads the extraction** instead of re-parsing the source.

`cad_drafter` is the best-written agent in the set, because CADCraft has the best agent interface
in the suite — `command_line` types at the command line exactly like a person
(`"line 0,0 @10,0 @0,5 c"`). The instructions use it as the primary verb.

---

## 5. Knowledge: where each kind of knowledge belongs

`skills: []` in the reference is empty. Here it is the primary knowledge channel, plus three
others.

| Knowledge | Where | Example |
|---|---|---|
| **Cross-cutting method** | `skills[]` per agent | `craft_perception` (the sensing ladder), `craft_artifacts` (publishing with provenance) |
| **App-specific quirks** | `instructions` in the agent | CADCraft fail-closed; gridcraft has no `ui_inspect` via MCP; soundcraft's `path` trap; DesignCraft's printing-items-only render |
| **Discoverable capability** | the app itself — `query_commands`, `query_tools` | Never hard-code command ids; discover them |
| **Per-deployment config** | `dynamic_fields` | `read_root`, `write_root`, headless-vs-bridge, which app this agent owns |
| **Live state** | MCP **resources** | `vectorcraft://object/{id}`, `lightcraft://library`, `photocraft://document` |

Two shared skills ship with every agent in all three teams:

**`craft_perception`** — the sensing ladder, cheapest first:

1. `query_ui` — full state as JSON. Costs a few hundred tokens. **Start here.**
2. `query_document` — layer tree, history, selection.
3. `see_element_state` — every widget with label and rect. Works even when occluded.
4. `see_document` — a render of the artwork. Deterministic, headless-safe.
5. `see_canvas` — the canvas region of the **live screen**, with overlays and the brush cursor.
6. `see_window` — everything, including chrome. Expensive. Last resort.

Plus: use `query_map`, never hand-convert coordinates; use `see_scopes` over pixels; use
`see_diff` to verify an edit instead of re-reading a full image.

**`craft_artifacts`** — publish with provenance via `team_asset_put`, verify a final deliverable
by bridging and calling `see_window`, and state limitations in the hand-off. *"An asset with a
stated limitation is usable; an asset with a hidden one is not."*

---

## 6. The universal rules block

Every agent in every team carries the same `COMMON_RULES`. Ten rules, each derived from a
documented upstream behaviour rather than invented:

1. **Claim before you touch.** One agent per app; on failure, blackboard and hand off — do not force.
2. **Checkpoint before you edit.** So a bad turn rolls back instead of being re-derived.
3. **Perceive before you act.** `query_ui` first, then look. Never guess zoom, selection, or dialogs.
4. **Re-render after you edit.** Verify with `query_document` (structure) *and* a render (pixels).
5. **Scopes over pixels.** Numeric readouts are exact; screenshots are not.
6. **Never retry a write.** A failed call may have landed. `query_document` first.
7. **Write to the asset store, not shared files.** Provenance, and no path collisions.
8. **Find commands, don't guess ids.** `query_commands(app, filter)`. Guessed ids waste the turn.
9. **Headless by default.** Bridge only for final verification or when a human is watching.
10. **Hand off explicitly.** What you produced, what you assumed, what the next agent needs.

Rule 6 comes straight from PhotoCraft's documented bridge behaviour: *"A transport failure while
sending a request or waiting for its reply … reports that the operation may have completed …
Edits are never automatically resent."*

---

## 7. Working the numbers

| Metric | Reference team | `craft_studio` |
|---|---|---|
| Agents | 7 | 11 |
| MCP servers | 1 | 1 |
| Tools per agent | 12–26 | 29–57 (leader 32, specialists 53–57, read-only 29) |
| Unique tools across the team | ~26 | 57 |
| Side-effect surface | read-only (telemetry) | 8 app specialists + read-only curator/QA |
| Apps reachable per agent | 1 (shared domain) | 1, by construction |
| Direct-registration equivalent | n/a | 12 servers, ~270 tools |

The team gets 57 tools where direct registration would put ~270 in one context — **and** it
gains app isolation, checkpoints, provenance and a rollback path, none of which direct
registration can provide.

---

## 8. Using these files

```sh
cd Scaico_Teams
python3 build_teams.py       # regenerate all three from build_teams.py
python3 validate_teams.py    # schema + invariants (must print FAILURES: 0)
```

Before use:

1. Replace `GATEWAY_URL` and `GATEWAY_TOKEN` in `build_teams.py`.
2. Set `agent_db_id` / `team_db_id` to match your database (currently 100–310 / 10–12).
3. Set `model` and `model_runtime` to your deployment.
4. Fill `dynamic_fields` per agent (roots, mode, owned app).

`validate_teams.py` enforces: identical key sets to the reference team at every level, the
top-level `agents` array mirroring `teams[0].agents`, no duplicate tool names, unique agent ids,
exactly one leader that resolves, `mcp_servers[].tools` equal to the agent's `tools`,
`streamable_http` transport with non-empty `url` and `token`, well-formed non-empty `skills`
(`{name, description, content}`) on every agent, `team_claim` + `team_checkpoint` on every agent
that holds an `act_*` tool, `job_wait` on every read-only agent, and **no `act_*` tool on any
leader, curator or QA agent**.

### 8.1 Adding an application

1. Add an `owned("<app>")` specialist to the appropriate roster.
2. Append its capability notes and traps to `instructions`.
3. Re-run both scripts. The validator is your guard.

### 8.2 Reducing the roster

The studio's 11 agents is the full suite. Most runs want fewer. Delete agents you do not need and
promote one of the remaining specialists to `team_leader` (set `type`, `team_leader_id`, and drop
its `act_*` tools if it must not edit). The leader needs no `act_*` tools to do its job — routing
is `team_notify` + `team_blackboard_write`.

---

## 9. Known open items

1. **`deckcraft`'s `call_app`** — the only existing cross-app primitive. Its target set was not
   traced. If it can invoke another Craft app, cross-app work may be simpler than the asset store.
   Until traced, the team config says to verify before relying on it and to prefer the asset store.
2. **GridCraft has no `ui_inspect` via MCP** and its `screenshot` returns JSON. The data analyst's
   instructions say to work from `query_document`/`query_ui` instead. A gateway-side fix (route
   `query_ui` through the control channel) would close this.
3. **PdfCraft's AccessKit widget tree is unreachable from MCP.** The most capable perception
   channel in the fleet, one transport away from being available.
4. **No `canvasRect` in photocraft**, despite `act_pointer` being document-space. The gateway must
   synthesise it for `see_canvas` to work there.
5. **No pointer position** in any app except CADCraft — hence `see_pointer` is a gateway-built
   tool.
6. **Instance scoping.** The teams assume the mutex is per app *instance*, not per app name, so
   concurrent sessions do not queue behind each other. That has to be true in the gateway.