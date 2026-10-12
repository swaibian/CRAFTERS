# CRAFTERS Final Demo — 4-Step Northstar (Lane 5, 2026-10-12)

Ship-readiness demo: gateway + controller + view, fake-backend mode (no `*-cli`
binaries installed), real local document adapters. Suites re-executed today:
gateway **188** (+9 skipped = real-CLI tests, no binaries) + controller **77** + view **72** = **337 passed, 0 failed**.

## Step 0 — Bring the stack up (pick ONE)

**Option A — Docker (ship path):**

```bash
cd deploy && docker compose up --build
```

- Chat UI: http://127.0.0.1:8791/ · Controller: http://127.0.0.1:8790/api/health
- Gateway MCP: http://127.0.0.1:8787/mcp (bearer enforced, fail-closed)
- Verified 2026-10-12: `docker compose config --quiet` OK; `build` OK
  (`crafters/gateway:local`, `crafters/controller:local`, `crafters/view:local`).
  `up` needs ports 8787/8790/8791 free — if the native stack (Option B) is
  already running, stop it first (port clash is expected, not a defect).

**Option B — Native (dev path):**

```bash
./start.sh                  # gateway :8787 + controller :8790 + view :8791
```

- Verified 2026-10-12 live: `:8790/api/health` → `{"ok":true}`, `:8791` → 200,
  `:8787/mcp` → HTTP 400 (server up; streamable_http needs session init).
- First run: open `#/settings`, add AI endpoint + key (Test-connection probes
  it) — or chat immediately with the built-in mock brain (labeled `mock:true`).

## Step 1 — PhotoCraft: drop → resize 800px (snapshot/render/assert/record)

1. In the chat UI picker, select **PhotoCraft**.
2. Drop a photo (`psd`/`jpg`/`png`) onto the dropzone → header shows name + app
   + inspect summary + thumbnail; chat binds to `doc_id`+`session_id`.
3. Send: **"resize to 800px"** (mock brain understands `resize/rotate/grayscale`
   phrasing; a real key handles free-form requests).
4. Expected agent loop (visible as toolcall blocks): `snapshot` (guard) →
   `photo.transform(resize, 800)` → re-read `inspect` (see: `width: 800`) →
   `assert` (structural) → `record` (claim ledger rides `response.completed`).
5. Re-executed 2026-10-12 (real files): `1600×1200 → 800×600`,
   hash `sha256:5d00a819… → sha256:cf64f929…`, revision bumped.

## Step 2 — Repeat for PdfCraft and GridCraft

- **PdfCraft**: drop a `.pdf` → send **"rotate page 0 by 90 degrees"** →
  `pdf.transform(rotate, page=0, degrees=90)` → verify `rotation:90`.
  Re-executed 2026-10-12: hash `sha256:b37a58fb… → sha256:23e1a110…`.
- **GridCraft**: drop an `.xlsx` → send **"set C3 to 99 and B2 to 7"** →
  `set_cell` × 2 → re-read shows `dims A1:C3`, sample `[[hi,…],[…,7,…],[…,99]]`.
  Re-executed 2026-10-12: hash `sha256:cc7a1e3c… → sha256:211ecb2f…`, rev 3.
- Download the edited copy from the thread (download route returns edited bytes;
  originals are never touched — adapters work on session copies).

## Step 3 — Bridge live GUI (verify what the app shows)

- Gateway perception tools (fake-mode canned shapes, live trees once CLIs +
  upstream PRs land): `craft_widgets` (widget tree, `focused` filter) and
  `craft_map` (`doc_to_screen`/`screen_to_doc`, `canvasRect` synthesis).
- In-chat verify buttons (Snapshot / Restore / Record-view) act on the open doc;
  `craft_look` returns metadata + content hash as the "see" step.
- NOT yet live: real CLI widget trees and pixel-diff asserts (need `*-cli`
  binaries + upstream `ui_inspect`/`canvasRect` PRs — drafts only, see TODO).

## Step 4 — Settings, teams, teardown

1. `#/settings`: profiles (masked keys, Test-connection), active profile,
   Scaico key + team select (no key → `contact@swaibian.com` mailto CTA),
   gateway endpoint. All persist server-side (`PUT /api/settings/*`).
2. With a team selected, chat runs are bound to `team_id` (teams-e2e test green).
3. Teardown: `Ctrl+C` (native) or `docker compose down` (compose). Data:
   `crafter-work` volume / `controller/work/` (session files),
   `crafter-settings` volume / `controller/settings.local.json` (keys, gitignored).

## What runs containerised vs local (2026-10-12)

| Piece | Containerised (`deploy/`) | Needs local binary / TODO |
|-------|---------------------------|---------------------------|
| Gateway tools (12) | ✅ image builds + serves (fake mode) | Real path needs `photocraft-cli`/`pdfcraft-cli`/`gridcraft-cli` on PATH (none installed) |
| Controller + adapters | ✅ image builds + serves; adapters edit real files | Real LLM needs user key in `#/settings` (mock until then) |
| View (chat UI) | ✅ node-build → nginx static, `/api` proxied (SSE no-buffer) | Dev mode needs local `node`/`npm` (Option B) |
| Gateway tokens | Fail-closed (no tokens baked) | Mint per session: `CRAFTER_DEV_TOKEN` (loopback only) or `CRAFTER_TOKENS_FILE` mount — never in images/logs |
| Upstream a11y PRs | n/a (docs only) | Drafts in `docs/upstream-prs/` — NOT submitted; TODO with URLs |
| Gateway healthcheck | ✅ fixed: MCP 4xx = healthy (needs bearer/session); only conn-fail/5xx unhealthy | — |

## Troubleshooting (from `deploy/README.md` + Lane 5)

| Symptom | Cause → fix |
|---------|-------------|
| `bind: address already in use` on `compose up` | Native stack already on the ports → stop it (`Ctrl+C`) or change ports |
| Chat says "controller unreachable" | Controller not running → start it (Step 0) |
| Agent replies "What should I change?" | Mock brain needs directive phrasing (`set A1 to X` / `resize to Npx` / `rotate page N`) or a real key |
| Gateway denies everything | No token provisioned → set `CRAFTER_DEV_TOKEN` (loopback) or mount tokens file |
| Gateway container shows "unhealthy" | Fixed 2026-10-12 (4xx-tolerant healthcheck); rebuild the image |
