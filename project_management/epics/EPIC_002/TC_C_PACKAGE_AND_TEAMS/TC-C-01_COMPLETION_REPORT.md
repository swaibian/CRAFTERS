# TC-C-01: Packaging — Completion Report

**Issue**: TC-C-01
**Component**: Package + Teams
**V-Model**: SWE3-C-01
**Type**: 🔨 IMPLEMENTATION
**Status**: ✅ Complete
**Completed**: 2026-10-12

---

## 1. What Was Built

### New Files

| File | Purpose | Serves |
|------|---------|--------|
| `deploy/Dockerfile.controller` | Controller image (code + adapter deps, non-root, `/work` + `/settings` mounts, `:8790`); settings arrive via volume, never baked | shippable controller |
| `deploy/Dockerfile.view` | View image (node build → nginx static, `/api` proxied to controller with SSE-friendly no-buffering) | shippable view |
| `deploy/nginx.view.conf` | Static + `try_files` (hash routes) + `/api/` proxy (`proxy_buffering off` for SSE) | view runtime |
| `deploy/README.md` | Fresh-checkout run (compose + native 3-terminal), first-run setup, troubleshooting table | run docs |
| `controller/tests/test_packaging.py` (6 tests) | Compose services/ports/volumes/health/logs; Dockerfiles bake no secrets (code lines scanned, comments exempt); nginx SSE proxy; README completeness | SWE4 |

### Changed Files

| File | Change |
|------|--------|
| `deploy/docker-compose.yml` | Added `controller` + `view` services, `crafter-settings` volume, native-run header, `CRAFTER_SETTINGS_FILE` wiring |

### APIs / Contracts Defined

| Module | API |
|--------|-----|
| Compose | `gateway :8787` + `controller :8790` + `view :80→8791`, all loopback-only; `crafter-work` + `crafter-settings` volumes; healthchecks (`/mcp` probe, `/api/health`) |
| Native run | 3 commands (gateway + controller + `vite dev`); ports match compose |

---

## 2. Key Decisions

| Decision | Rationale |
|----------|-----------|
| Secrets test scans code lines only, comments exempt | Dockerfiles must *document* the no-secrets rule in comments — the test pins the rule, not the docs |
| nginx `proxy_buffering off` + 300s read timeout | SSE streams break under buffering/proxy timeouts |
| Native-run docs as first-class (not compose-only) | User tests natively today; compose is the ship path |

---

## 3. Gate Results

| Gate | Result | Notes |
|------|--------|-------|
| Pre-check test suite (Task 0.2) | ✅ suites green | no regressions |
| Post-implementation suite (Task 6) | ✅ controller 46 passed (40 + 6 packaging) | 0 failures |
| Coverage vs baseline | ✅ no regressions | packaging statically validated |
| Typecheck / Lint | ✅ compileall + ruff clean | MANDATORY — met |
| Fresh-checkout validation | ✅ `docker compose config` valid; native 3-service run proven live (`:8787/:8790/:8791`) | — |

## 3.5 Logger Evidence (mandatory)

| Item | Evidence |
|------|----------|
| Compose logging | json-file, `max-size 10m × 3` on all services (disk blowup bounded) |
| No secrets in container logs | Dockerfiles bake none (tested); settings volume never logged; controller redaction tests cover runtime |
| Audit/metrics separation | N/A (packaging); documented |

---

## 4. Handoff for TC-C-02 (Teams E2E + Closer)

**Entry point**: `controller/settings.py::list_teams` + `Scaico_Teams/teams/*.json` — wire team select → agent session end-to-end, then close TC-C and EPIC_002.

**What you inherit**: Full stack (this TC); `PUT /api/settings/team` + `GET /api/teams` live; team JSONs carry per-agent `model_runtime` (provider + base URL) usable as profile hints.

**What is NOT implemented yet** (TC-C-02 owns): team→session e2e wiring test + fallback/direct verification, closer duties, EPIC_002 boundary.

**Run tests**: `python3 -m pytest controller/tests/ -q` from repo root.

---

## Traceability

| Level | ID | Artifact |
|-------|-----|---------|
| SYS1 | SYS1-002 | Epic: EPIC_002_CRAFTER_CHAT_UI.md |
| SWE1 | SWE1-C | TC: TC-C-00_COMPONENT_DEFINITION.md |
| SWE3 | SWE3-C-01 | Issue: TC-C-01_PACKAGING.md |
| SWE4 | packaging tests | `controller/tests/test_packaging.py` (6) |

---

## Self-verification (no-reviews mode)

| Gate | Command | Exit | Result |
|------|---------|------|--------|
| D1 Lint | `ruff check/format controller/` | 0 | clean |
| D2 Typecheck | `compileall controller` | 0 | clean |
| D3 Tests | `pytest controller/tests/` | 0 | 46 passed |
| D4 Compose validation | `docker compose config` + live native 3-service run | 0 | valid + serving |
| D5 Self-checklist | every file → SW-REQ-PACK; impl + test; no secrets baked (tested); boxes ticked | — | yes to all |

Independent review intentionally omitted — TC-C is declared `no-reviews`; gap analysis is inherited by the TC closer (TC-C-02).

## Lane 5 audit (2026-10-12) — executed evidence

- Re-ran: `controller/tests/` → **77 passed** (was 46 at writing, incl. 6 packaging tests).
- `docker compose -f deploy/docker-compose.yml config --quiet` → OK; `docker compose build` → **gateway/controller/view images Built** (executed this lane).
- `docker compose up` was attempted: blocked only by port clash with the already-running native stack (`:8787` in use by another lane's `start.sh`) — not a deploy defect; partial containers removed via `down`.
- Verdict: KEEP ✅ Complete — compose validity + image builds executed. Gateway runs containerised in fake-backend mode until `*-cli` binaries exist (see DEMO.md containerised-vs-local table).
