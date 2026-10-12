# HANDOVER — Execute the Crafter Northstar: Real Craft Apps, Driven Live

> **For**: the next implementation team (fresh agents, no prior context).
> **Date**: 2026-10-12 · **Repo root**: `05_Products/Crafters/`
> **Prior state**: gateway + controller + view scaffolding exists, 158 gateway tests pass —
> but **everything runs against `FakeAppBackend`**. No real Craft CLI has ever been spawned.
> Your job: make the northstar real.

---

## 1. Northstar (do not dilute this)

> **Agents that work inside the real application** — via stdio MCP subprocess +
> loopback control channel + bridge mode — through one gateway, chatted with in one UI.

Concretely, when you are done, a user can:

1. `docker compose up` (or run locally), open the Chat UI, pick **PhotoCraft**,
2. drop a real `.psd`/`.jpg`, watch the agent open it **in a real `photocraft-cli` process**,
3. ask "resize to 800px", and see the agent run real engine commands, snapshot before the edit,
   render the result, assert the new size, and record the claim with evidence —
4. then repeat for PdfCraft and GridCraft, and see the live GUI move in bridge mode.

Anything that does not serve that demo is out of scope. No new epics, no refactors, no
"improvements" to working code unless a gate forces it.

---

## 2. Ground truth (verified 2026-10-12, trust this over any doc)

| Fact | Evidence |
|:-----|:---------|
| Gateway + controller + view code exists | `gateway/*.py` (~3.9k lines), `controller/*.py`, `view/src/` |
| **158/158 gateway tests pass** | `python3 -m pytest gateway/tests/ -x -q` |
| **No Craft CLI binaries installed** | `which photocraft-cli pdfcraft-cli gridcraft-cli` → all "not found" |
| **Rust sources ARE on disk** | `~/Downloads/CRAFT/{photocraft,pdfcraft,gridcraft,lightcraft,vectorcraft,wordcraft}-main/` (source only, `apps/<app>-cli/` present, **no built binaries**) |
| Backend falls back to `FakeAppBackend` when CLI absent | `gateway/backends.py:11`, `BackendManager(use_fake=...)`, all integration tests use `use_fake=True` |
| Real proxy path exists but is unexercised | `AppBackend`: "spawns the real CLI over stdio (FastMCP `Client` + `StdioTransport`)" — zero tests cover it against a real binary |
| Work is uncommitted | `git status`: `gateway/ controller/ view/ deploy/ docs/` etc. all untracked; last commit is chore/docs only |
| Toolchain ready | Python 3.14.2, fastmcp 2.14.5, mcp 1.26.0, pytest 9.0.2 |
| Research base (read, don't redo) | `project_management/_templates/raw_Repository_findings/00–08` + `SOURCES.md` |
| Plan base (follow, don't reinvent) | `project_management/epics/EPIC_001_CRAFTER_GATEWAY.md`, `EPIC_002_CRAFTER_CHAT_UI.md`, `EPIC_OVERVIEW.md`, `architecture/` |
| Team definitions (already generated) | `Scaico_Teams/teams/craft_{studio,motion,documents}_2026-10-11.json` + `build_teams.py` + `validate_teams.py` |

---

## 3. Workstreams — parallelise with subagents (5 lanes, minimal interfaces)

Spawn **one subagent per lane** in parallel. Lanes sync only at the interfaces listed. A lane
that is blocked >30 min must post its blocker to the shared log and pick up the fallback.

### Lane 1 — Build the pilot CLIs (unblocks Lanes 2+3)

- **Goal**: working `photocraft-cli`, `pdfcraft-cli`, `gridcraft-cli` binaries on this machine.
- **Sources**: `~/Downloads/CRAFT/{photocraft,pdfcraft,gridcraft}-main/` (full Rust sources).
- **Steps**: `cargo build --release -p <app>-cli` per app (expect long first builds; run in
  parallel shells or background). Verify each binary answers `<app>-cli mcp --help` (or the
  documented equivalent in `raw_Repository_findings/05-QUICKSTART.md`).
- **Fallback if a build fails**: (a) `cargo build -p <app>-cli` debug build; (b) document the
  exact blocker and ship the other two apps — do NOT stall all lanes on one app.
- **Interface out**: absolute binary paths → append to `deploy/local-bin-paths.env`
  (create it; format `PHOTOCRAFT_CLI=/path/...` one per line). Commit nothing with secrets.
- **Done when**: all three binaries (or documented subset) respond to an MCP `tools/list`
  over stdio by hand (`echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | <bin> mcp`).

### Lane 2 — Real-backend integration (needs Lane 1 paths, can start with fakes→real swap)

- **Goal**: `AppBackend` drives a **real** CLI subprocess end-to-end; `FakeAppBackend` becomes
  opt-in (`use_fake=True` explicit), never the silent default.
- **Files**: `gateway/backends.py`, `gateway/tools_phase1.py`, `gateway/tools_phase2.py`,
  `gateway/tests/`.
- **Steps**:
  1. Read `gateway/backends.py` fully (esp. `AppBackend`, `BackendManager`, `SessionRegistry.check_path`).
  2. Add `CRAFTER_CLI_PATHS` env/file config (read `deploy/local-bin-paths.env` from Lane 1).
  3. Invert the fallback: real backend is default; fake only on explicit flag or binary-missing
     **with a loud warning** (log + `craft_status` field `mode: "fake"`).
  4. Write `test_backends_real.py`: spawn each pilot CLI, `tools/list`, one harmless read-only
     call per app (e.g. `command_list`/`doc_inspect` on empty session), assert real (non-fake)
     responses. Mark `pytest.mark.real` so CI-without-binaries can `-m "not real"`.
  5. Run one full Phase-1+2 cycle by hand against a real app: open doc → snapshot → edit →
     look → assert → record. Paste the transcript into the completion report.
- **Done when**: `pytest -m real` passes on this machine AND the hand transcript shows a real
  edit + render + assert through the gateway.

### Lane 3 — Bridge mode to live GUIs (needs Lane 1 binaries, independent of Lane 2)

- **Goal**: drive a **running desktop app** over its loopback control channel and see the window move.
- **Sources**: `raw_Repository_findings/01-RESEARCH-FINDINGS.md` §5 (control protocol table),
  `05-QUICKSTART.md` (bridge commands per app), app repos' `docs/control-protocol.md`.
- **Steps**:
  1. Launch one pilot desktop binary with its control port
     (e.g. `photocraft --control 7878 --control-token-file /tmp/...` — exact flags in QUICKSTART).
     Headless Linux/macOS: expect a window or an offscreen failure — **document exactly what
     happens**; if no display exists, use Xvfb or the documented headless-serve mode instead
     and say so explicitly.
  2. Send one raw control call by hand (`ui.inspect` / `engine.commands`) and capture the reply.
  3. Wire the smallest possible bridge path in the gateway (reuse `control_call`/`call_app`
     passthrough tools): `craft_app_call {app, method, params}` → TCP JSON-lines → reply.
  4. Prove it: `craft_look` in bridge mode returns a window screenshot that differs from the
     headless render (or document precisely why it cannot on this host).
- **Fallback**: if no GUI can run on this host, deliver (a) the raw-protocol transcript,
  (b) the bridge client code + tests against a loopback stub server, (c) a written runbook for
  the machine with a display. Do NOT fake a screenshot.
- **Done when**: transcript of a real control-channel round-trip + working `craft_app_call`
  (against live app or stub, clearly labelled which).

### Lane 4 — View + controller wiring to real gateway (independent, start now)

- **Goal**: Chat UI talks to the **real** gateway/controller, not mocks; drop→open→chat→verify
  works against Lane 2's backend.
- **Files**: `view/src/`, `controller/service.py`, `controller/agent.py`, `controller/documents.py`.
- **Steps**:
  1. Inventory every mock/fallback in `view/src/lib/api.ts` and the components (search
     `mock|fallback|unreachable`); list which controller endpoints are missing.
  2. Implement the missing controller endpoints (follow existing `controller/service.py` patterns;
     per-user denial + session isolation + no token leakage on every new endpoint).
  3. Point the view at the real endpoints; keep mock fallbacks **only** as visibly-labelled
     offline notices, never silent.
  4. End-to-end smoke: drop a file in the UI → opens via gateway → chat message streams back
     (mock LLM acceptable, but the **file-open and tool path must be real**).
- **Done when**: UI drop→open→chat works against the real gateway with a real CLI behind it
  (coordinate a joint smoke with Lane 2).

### Lane 5 — Docs, gates & ship readiness (independent, start now)

- **Goal**: make the work shippable and auditable without slowing the other lanes.
- **Steps**:
  1. `git add` the untracked work in small, reviewable commits (gateway, controller, view,
     deploy, docs separately; never commit secrets, tokens, or `settings.local.json`).
  2. Fix `deploy/` so `docker compose up` (or `start.sh`) brings up gateway+view; document
     exactly what still needs a local binary vs. what runs containerised.
  3. Update the 12 completion reports **only with executed evidence** (gate tables, transcripts,
     smoke logs). Reports currently say ✅ Complete — downgrade any claim not backed by a real
     run to 🔲 with a reason.
  4. Update `EPIC_OVERVIEW.md`, epic files, and `architecture/` change log to match reality.
  5. Produce the final demo script (the 4-step northstar demo above) as `docs/DEMO.md`.
- **Done when**: fresh-checkout (or fresh-clone + documented binary step) reaches the demo,
  and every completion report is evidence-backed.

---

## 4. Rules of engagement (all lanes)

1. **Real over fake, always.** A failing real call beats a passing fake. Never mark done on fakes.
2. **Evidence in reports.** Every completion report gets: commands run, exit codes, transcripts,
   test counts. "Works" without a transcript did not happen.
3. **Small commits, no secrets.** Tokens/keys/PII never in git, logs, or reports. Redaction tests stay green.
4. **Follow the plan files.** `EPIC_001/002`, TC definitions, `08-REQUIRED-TOOLS.md` Phase 1+2,
   `04-SECURITY.md` containment. Deviations go in the report with rationale, not in silence.
5. **Tests stay green.** `pytest gateway/tests/` (158 baseline) + view `npm test` must pass at
   every commit. New real-backend tests get `pytest.mark.real` for binary-less CI.
6. **Sync at interfaces only.** Lanes 2/3 consume `deploy/local-bin-paths.env` from Lane 1;
   Lane 4 consumes Lane 2's tool contracts; Lane 5 observes all. No other cross-lane blocking.
7. **Timebox builds.** Rust release builds are slow — start Lane 1 first, background them, and
   begin Lane 2/4 against fakes with the real-swap as the defined second step.

---

## 5. Definition of done (whole handover)

- [ ] Three (or documented subset) pilot CLIs built from `~/Downloads/CRAFT` sources.
- [ ] Gateway spawns real CLIs by default; `pytest -m real` passes; hand transcript of
      open→snapshot→edit→look→assert→record against a real app exists.
- [ ] Bridge-mode transcript exists (live app or stub+runbook, clearly labelled).
- [ ] UI drop→open→chat→verify works against the real gateway (joint smoke with Lane 2).
- [ ] `docker compose up` (or `start.sh`) + `docs/DEMO.md` reproduces the 4-step northstar demo.
- [ ] All 12 completion reports evidence-backed; EPIC_OVERVIEW + epics + architecture log match reality.
- [ ] Full test suites green; work committed in small commits; no secrets committed.

---

## 6. First actions (do these in order, now)

1. Spawn 5 subagents, one per lane above; paste each lane's section verbatim as its brief.
2. Lane 1 starts `cargo build --release -p <app>-cli` immediately (background, parallel).
3. Lanes 4+5 start immediately (no dependencies).
4. Lanes 2+3 read code/docs while Lane 1 builds, then execute on binaries.
5. You (coordinator) track `deploy/local-bin-paths.env` as the unblock signal for Lanes 2+3,
   and run the joint Lane 2+4 smoke before calling the handover done.
