# Lane 3 — Bridge-mode runbook (drive a live Craft window)

Status on this host (2026-10-12, macOS arm64): **fallback path**. No pilot
binary exists here yet (Lane 1 still building; `which photocraft-cli
gridcraft-cli pdfcraft-cli` → not found, no `target/` dir in the source
checkouts), so no GUI could be launched. What *is* proven here: the exact
wire protocol against a loopback stub (`gateway/tests/test_bridge.py`, 25
tests), the gateway wiring (`craft_app_call` → TCP JSON-lines), and the
`craft_look(scope="window")` window-vs-headless proof shape. Follow §5 on a
machine with a display + built binaries for the live-window proof.

## 1. Control-protocol findings (pilot apps)

Sources: `01-RESEARCH-FINDINGS.md` §5, `05-QUICKSTART.md` §3, and the app
repos' `docs/control-protocol.md` + `apps/*/src/control_server.rs` /
`main.rs` (verified, not just copied).

| App | Transport | Auth | Launch (bridge mode) |
|---|---|---|---|
| photocraft | TCP loopback | **Bearer token, auth frame first on every connection.** Token via `--control-token-file <path>` (file `0600`, never on cmdline), `PHOTOCRAFT_CONTROL_TOKEN[_FILE]` env. No token configured → app prints a fresh one to stderr. | `photocraft --control 7878 --control-token-file /tmp/pc.token --automation-read-root R --automation-write-root W` then `photocraft-cli mcp --bridge 127.0.0.1:7878 --control-token-file /tmp/pc.token` |
| gridcraft | TCP loopback, **no auth** (verified in `apps/gridcraft/src/control_server.rs`: every line is dispatched, no token check) | none | `gridcraft --control 7979 [--sample sales]` then `gridcraft-cli mcp --connect 7979` (also `GRIDCRAFT_CONTROL_PORT=7979`) |
| pdfcraft | **No TCP control channel.** Control surface is in-process (`crates/ui-egui` `ControlClient`: `ui.state`, `ui.command`, `ui.set`, … — see `crates/ui-egui/tests/control.rs`). CLI entry is file-based per QUICKSTART: `pdfcraft-cli ui --control FILE <method>` | n/a (file perms) | `pdfcraft --control ~/.pdfcraft-control.json`, then `pdfcraft-cli ui --control ~/.pdfcraft-control.json <method>` |

Wire format (TCP apps, identical): one `{"id","method","params"}` JSON
object per line → one `{"id","ok","result"|"error"}` line back, same `id`.
Key methods: `engine.execute {command, params, wait?}` (universal),
`engine.commands {filter?/search?}`, `ui.inspect`, `ui.set`,
`ui.menu.invoke/list`, `ui.pointer/click/key/type`, dialog verbs,
`ui.screenshot {path?, focus?}` (base64 PNG when no path; raises the window
first — occluded macOS windows stop rendering), `app.open/save/quit`,
`jobs.list/cancel`. Transport ceilings: 1 MiB request line, 8 MiB reply,
16 conns, 30 s socket timeout, desktop waits ≤60 s per call (bridge times
out at 55 s, strictly lower). Per-connection idle close ≈30 s — reconnect
per call batch if idle. Gotchas: Wayland frame-callback starvation (occluded
window ⇒ timeouts on a healthy app), bridge edits are never auto-retried
(reads get one retry).

## 2. Launch attempts on this host (exact outcomes)

```sh
$ which photocraft photocraft-cli gridcraft-cli pdfcraft-cli
photocraft not found / photocraft-cli not found / gridcraft-cli not found / pdfcraft-cli not found
$ echo "DISPLAY=${DISPLAY:-<unset>}"   # → DISPLAY=<unset>
$ which Xvfb xvfb-run                  # → not found (X11-only tools; N/A on macOS anyway)
$ ls ~/Downloads/CRAFT/gridcraft-main/target   # → No such file or directory
```

Outcome: **no launch possible** — binaries absent (Lane 1 dependency) and
no control port to dial. No headless-serve substitute exists for the
*desktop* binary (only `photocraft-cli serve` exists, and the CLI is also
unbuilt). Nothing was faked: no screenshot is claimed anywhere in this
lane's evidence.

## 3. Raw control transcripts (captured live, loopback stub on this host)

Stub: `StubControlServer` in `gateway/tests/test_bridge.py` — speaks the
real wire format (verified against `control_server.rs`: no-auth dispatch
for gridcraft; auth-frame-first for photocraft). Token `tok-abc` below is a
test value, not a secret.

Gridcraft-style (no auth), stub on `127.0.0.1:54682`:

```
C: {"id":1,"method":"ui.inspect","params":{}}
S: {"id": 1, "ok": true, "result": {"tool": "select", "windows": 1, "mode": "stub"}}
C: {"id":2,"method":"engine.commands","params":{}}
S: {"id": 2, "ok": true, "result": {"commands": [{"id": "cell.set"}, {"id": "file.new"}]}}
```

Photocraft-style (auth frame first), stub on `127.0.0.1:54695`:

```
C: {"id":"auth","method":"auth","params":{"token":"tok-abc"}}
C: {"id":1,"method":"ui.inspect","params":{}}
S: {"id": "auth", "ok": true}
S: {"id": 1, "ok": true, "result": {"tool": "select", "windows": 1, "mode": "stub"}}
```

(`test_wire_transcript_exact_bytes` + `test_bridge_client_auth_frame_first`
pin these bytes; the client sends compact JSON, the stub replies as above.)

## 4. Bridge code (what changed, tests)

- **`gateway/bridge.py` (new)** — `BridgeConfig` (host/port/token/
  token-file/inspect-style/timeout), `BridgeClient` (loopback-only dial,
  auth frame, `call(method, params)` with stale-id skipping, 1 MiB / 8 MiB
  caps, 55 s default timeout), `bridges_from_env()` (`CRAFTER_BRIDGE_<APP>`
  = `host:port`, `<APP>_TOKEN_FILE` for the token path), and
  `summarize_screenshot()` (base64 PNG → `{content_hash: sha256:…,
  source: bridge-window, width, height}`; image bytes never leave it).
- **`gateway/backends.py`** — `BridgeAppBackend` (verbatim
  `call_tool(method, params)` passthrough = the `craft_app_call` escape
  hatch, plus read-only aliases `doc_inspect` → `document.inspect` /
  `engine.execute document.inspect` and `render_preview` → `ui.screenshot`
  metadata) and `BackendManager(bridges={...})` (bridge wins over the CLI
  subprocess; **fail-closed**: a down app raises instead of degrading to a
  fake, so a bridge aimed at a live window can never silently edit a
  headless document; `status()` reports `running/mode: bridge`).
- **`gateway/tests/test_bridge.py` (new, 25 tests)** — client, auth,
  stale-skip, loopback refusal, screenshot hashing, backend aliases,
  manager sharing + fail-closed, `craft_app_call` and
  `craft_look(scope="window")` end-to-end. `craft_look` in bridge mode
  returns `source: bridge-window` with `content_hash` over the window
  pixels, provably ≠ headless `sha256:fake`.
- Full suite: `python3 -m pytest gateway/tests/ -q` → green (was 163
  passed / 9 skipped before this lane; bridge file adds 25).

## 5. Live-window runbook (machine with display + Lane 1 binaries)

```sh
# 1. Start the app with its control channel (gridcraft needs no token).
gridcraft --control 7979 &
#   photocraft instead:
# photocraft --control 7878 --control-token-file /tmp/pc.token \
#   --automation-read-root /work --automation-write-root /work &

# 2. Raw control call by hand (gridcraft: no auth frame needed).
python3 -c "
import json, socket
s = socket.create_connection(('127.0.0.1', 7979), timeout=60)
f = s.makefile('rw')
f.write(json.dumps({'id': 1, 'method': 'ui.inspect', 'params': {}}) + '\n'); f.flush()
print(f.readline())   # expect {"id":1,"ok":true,"result":{...windows, ribbon, grid rect...}}
"
#   photocraft: first line must be
#   {"id":"auth","method":"auth","params":{"token":"$(cat /tmp/pc.token)"}},
#   then the ui.inspect line; expect {"id":"auth","ok":true} first.

# 3. Bridge through the gateway (same host).
export CRAFTER_BRIDGE_GRIDCRAFT=127.0.0.1:7979
#   photocraft instead:
# export CRAFTER_BRIDGE_PHOTOCRAFT=127.0.0.1:7878
# export CRAFTER_BRIDGE_PHOTOCRAFT_TOKEN_FILE=/tmp/pc.token
python3 - <<'EOF'
import asyncio
from gateway.backends import BackendManager
from gateway.bridge import bridges_from_env
from gateway.tools_phase1 import Phase1Tools
from gateway.tools_phase2 import Phase2Tools
async def main():
    mgr = BackendManager(apps=('gridcraft',), bridges=bridges_from_env(('gridcraft',)))
    p1, p2 = Phase1Tools(mgr), Phase2Tools(mgr)
    print(await p1.craft_app_call(app='gridcraft', method='ui.inspect', params={}))
    print(await p2.craft_look(app='gridcraft', scope='window'))  # source: bridge-window
    await mgr.close_all()
asyncio.run(main())
EOF

# 4. See the window move (gridcraft): resize + screenshot, compare hashes.
#   craft_app_call {method: ui.resize, params: {width, height}} (or ui.focus),
#   then craft_look(scope=window) twice — hashes must differ from each other
#   across a resize and from any headless render_preview hash.
```

## 6. CRAFTERS app wiring (controller + view, 2026-10-12)

The gateway bridge above is now wired into the app the user sees:

- **Gateway** (`gateway/main.py`): builds `BackendManager(bridges=…)` from
  `CRAFTER_BRIDGE_<APP>` env (per-app fault isolation — one malformed var
  is skipped loudly, the rest stay live). No env vars = headless CLI mode,
  exactly as before.
- **Controller** (`controller/live.py`, `GET /api/live/status`,
  `GET /api/live/documents`, `POST /api/live/attach`): probes the control
  channel, lists open documents (`ui.inspect.session.documents`, active
  index), and attaches a document as the chat object. Attach is an
  **import**: the window is snapshotted via `ui.screenshot` into the
  session work dir and registered as a normal photo doc with
  `source="live"` provenance — chat, thumbnail, download, snapshot/restore
  and the agent edit loop work unchanged, on the copy, never on the live
  window. Errors are honest: down app → 502 naming the `--control`
  command; occluded window → 502 (focus the app and retry).
- **View** (`LiveApp.tsx`, section *3 · Live app window*): status rows with
  Refresh, per-app open-document list, *Use as chat object* (binds chat
  like an upload; the opened-file header badges `live window (photocraft)`),
  and — for TCP apps that are down — a **Launch** button
  (`POST /api/live/launch`, `controller/live.py::launch_app`): the
  controller spawns the allowlisted desktop binary with fixed argv (token
  via a 0600 file, never logged), registers its control channel, and polls
  until it answers. pdfcraft has no TCP channel, so it stays manual-entry
  only (409 with the hint). Desktop binaries resolve via
  `CRAFTER_DESKTOP_<APP>` or `PATH` (`start.sh` exports them when found);
  missing binary → honest 502 + the copy-paste start command.

Verified: `controller/tests/test_live.py` (14 tests, wire-format stub with
photocraft-style auth) + `LiveApp.test.tsx` (3 tests) + live smoke test
through real processes (status → documents → attach → mock chat
`response.completed`). Full suites: 288 Python + 77 view green.

To test with a real window: build the desktop binary
(`cargo build --release --bin photocraft` in `photocraft-main`), start it
per §5 step 1, export the two `CRAFTER_BRIDGE_PHOTOCRAFT*` vars, then
`./start.sh` — or just press **Launch** in section *3 · Live app window*
(needs the binary on `PATH` or `CRAFTER_DESKTOP_<APP>` set).

Per-OS notes (Launch works on all three — same button, same endpoint):
macOS/Linux detach via `setsid`, Windows via `DETACHED_PROCESS |
CREATE_NEW_PROCESS_GROUP` (no console window). The child inherits the
server environment: on Linux it needs `DISPLAY`/`WAYLAND_DISPLAY` (headless
servers: Xvfb or the app's offscreen mode); on macOS the controller must run
in a logged-in Aqua session (a bare SSH/daemon session has no window server
— Launch then times out honestly, Refresh retries). Windows resolves
`photocraft.exe` via `PATHEXT`; dev entry point there is `start.ps1`
(PowerShell mirror of `start.sh`).

Troubleshooting: connection refused → app not started with `--control`;
auth rejected → token file mismatch (photocraft rotates only when the file
is absent — keep the file); timeouts on healthy app → window occluded /
minimised (Wayland/macOS stop rendering hidden windows — `ui.focus` first);
`unknown method` → check `engine.commands` for the exact id.
