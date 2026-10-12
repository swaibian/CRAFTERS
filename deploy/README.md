# Run Crafter Chat (fresh checkout)

Three services: **gateway** (`:8787`, MCP tools), **controller** (`:8790`,
settings + agent loop + docs), **view** (`:8791`, chat UI).

## Option A — Docker (recommended)

Prereqs: Docker + Docker Compose.

```bash
cd deploy && docker compose up --build
```

- Chat UI: http://127.0.0.1:8791/ (pick app → drop file → chat; setup at `#/settings`)
- Controller: http://127.0.0.1:8790/api/health
- Gateway MCP: http://127.0.0.1:8787/mcp (bearer enforced)

First run: open `#/settings`, add your AI endpoint + key (Test-connection
probes it), pick it active — or chat immediately with the built-in mock
brain (clearly labeled, edits real file copies, no key needed).

Data: `crafter-work` volume (session files), `crafter-settings` volume
(endpoint/key JSON — never in images or logs).

## Option B — Native (3 terminals, repo root)

Prereqs: Python 3.12+ (`pip install -r gateway/requirements.txt -r
controller/requirements.txt`), Node 22+ (`npm --prefix view install`).

```bash
CRAFTER_DEV_TOKEN=dev-local-token CRAFTER_WORK_DIR=/tmp/crafter-work \
  python3 -m gateway.main --transport http --port 8787
python3 -m uvicorn controller.service:app --host 127.0.0.1 --port 8790
npm run dev --prefix view -- --host 127.0.0.1 --port 8791
```

Then open http://127.0.0.1:8791/.

## Troubleshooting

| Symptom | Cause → fix |
|---------|-------------|
| Chat says "controller unreachable" | Controller not running → start it (Option B line 2) or `docker compose up controller` |
| Agent replies "What should I change?" | Mock brain didn't parse the request → phrase as "set A1 to X" / "resize to Npx" / "rotate page N"; or add a real key in settings |
| Gateway denies everything | No token provisioned → set `CRAFTER_DEV_TOKEN` (loopback only) or mount `CRAFTER_TOKENS_FILE` |
| Real Craft CLIs ignored | No `*-cli` binaries installed → gateway uses fake backends (documented); doc adapters still edit real files |
| Port clash | Change ports in compose / CLI flags; update the gateway endpoint in `#/settings` |
