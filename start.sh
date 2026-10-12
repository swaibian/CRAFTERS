#!/usr/bin/env bash
# Start the full Crafter Chat stack locally (no .app/.exe build, no Docker).
#
# Services (all loopback-only):
#   gateway     http://127.0.0.1:8787/mcp  (MCP tools, bearer enforced)
#   controller  http://127.0.0.1:8790/api/health
#   view        http://127.0.0.1:8791/      (chat + #/settings)
#
# Usage:
#   ./start.sh                  # start all three, open browser, Ctrl+C to stop
#   ./start.sh --no-open        # don't open the browser
#   ./start.sh --no-view        # gateway + controller only
#   ./start.sh --stop           # kill the stack and exit (no start)
#   ./start.sh --help           # all options
#
# Pre-start cleanup (default on): stale holders of the three ports are stopped
# automatically; foreign processes are only killed with --force.
#
# Logs: .local-run/<service>.log
# Data: controller/work/ (session files), controller/settings.local.json (keys)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT/.local-run"
WORK_DIR="$ROOT/controller/work"

HOST="127.0.0.1"
GW_PORT="8787"
CTRL_PORT="8790"
VIEW_PORT="8791"
OPEN_BROWSER=1
WITH_VIEW=1
WITH_GATEWAY=1
AUTO_CLEANUP=1
FORCE_KILL=0
STOP_ONLY=0

usage() {
  sed -n '2,16p' "$0"
  echo ""
  echo "Options:"
  echo "  --host H             bind host (default 127.0.0.1, keep loopback for dev token)"
  echo "  --gateway-port P     default 8787  (--no-gateway to skip)"
  echo "  --controller-port P  default 8790"
  echo "  --view-port P        default 8791  (--no-view to skip)"
  echo "  --no-gateway         skip the MCP gateway"
  echo "  --no-view            skip the web UI"
  echo "  --no-open            don't open the browser"
  echo "  --no-cleanup         don't kill stale processes on the ports (default: auto-cleanup)"
  echo "  --force              kill whatever holds the ports, even if not ours"
  echo "  --stop               kill our services (or port holders) and exit, don't start"
  echo "  --help               this text"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST="${2:?}"; shift 2 ;;
    --gateway-port) GW_PORT="${2:?}"; shift 2 ;;
    --controller-port) CTRL_PORT="${2:?}"; shift 2 ;;
    --view-port) VIEW_PORT="${2:?}"; shift 2 ;;
    --no-gateway) WITH_GATEWAY=0; shift ;;
    --no-view) WITH_VIEW=0; shift ;;
    --no-open) OPEN_BROWSER=0; shift ;;
    --no-cleanup) AUTO_CLEANUP=0; shift ;;
    --force) FORCE_KILL=1; shift ;;
    --stop) STOP_ONLY=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "unknown flag: $1 (try --help)" >&2; exit 2 ;;
  esac
done

die() { echo "start.sh: $*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

have python3 || die "python3 not found"
[[ $WITH_VIEW -eq 0 ]] || { have node || die "node not found"; have npm || die "npm not found"; }

port_busy() { python3 -c "import socket,sys; s=socket.socket(); s.settimeout(0.5); sys.exit(0 if s.connect_ex(('$HOST',$1))==0 else 1)" 2>/dev/null; }

# -- Pre-start cleanup: reclaim stale ports ------------------------------------
pids_on_port() { # pids_on_port <port> — PIDs in LISTEN state only
  local port="$1"
  if have lsof; then
    lsof -ti "tcp:${port}" -sTCP:LISTEN 2>/dev/null || true
  fi
}

proc_cmd() { ps -p "$1" -o command= 2>/dev/null || echo "?"; }

is_ours() { # is_ours <cmdline> — is this one of our stack processes?
  case "$1" in
    *gateway.main*|*controller.service*|*Crafters/view*|*vite*|*uvicorn*controller*) return 0 ;;
    *) return 1 ;;
  esac
}

reclaim_port() { # reclaim_port <port> <label> — TERM→KILL holders, wait for free
  local port="$1" label="$2" pids pid cmd foreign=0
  port_busy "$port" || return 0
  pids="$(pids_on_port "$port")"
  if [[ -z "$pids" ]]; then
    echo "→ port $port ($label) busy but holder PID not found — waiting briefly…"
    for _ in $(seq 1 10); do port_busy "$port" || return 0; sleep 0.5; done
    die "port $port ($label) still busy — process holder unknown (try --force or lsof -ti tcp:$port)"
  fi
  for pid in $pids; do
    cmd="$(proc_cmd "$pid")"
    if is_ours "$cmd"; then
      echo "→ reclaiming port $port ($label): stopping stale ours PID $pid ($cmd)"
    else
      foreign=1
      echo "→ port $port ($label) held by foreign PID $pid ($cmd)"
    fi
  done
  if [[ $foreign -eq 1 && $FORCE_KILL -eq 0 ]]; then
    die "port $port ($label) held by a foreign process — refusing to kill (use --force to override, or --no-cleanup to fail fast)"
  fi
  [[ $foreign -eq 1 ]] && echo "→ --force: killing foreign holder(s) on port $port ($label): $pids"
  for pid in $pids; do
    pkill -P "$pid" 2>/dev/null || true
    kill "$pid" 2>/dev/null || true
  done
  for _ in $(seq 1 10); do port_busy "$port" || { echo "✓ port $port ($label) free"; return 0; }; sleep 0.5; done
  # Escalate to SIGKILL (npm/vite may not forward TERM).
  for pid in $pids; do
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
    pkill -9 -P "$pid" 2>/dev/null || true
  done
  for _ in $(seq 1 10); do port_busy "$port" || { echo "✓ port $port ($label) free"; return 0; }; sleep 0.5; done
  die "port $port ($label) still busy after kill — check lsof -ti tcp:$port"
}

if [[ $STOP_ONLY -eq 1 ]]; then
  echo "→ stop mode: reclaiming stack ports…"
  [[ $WITH_GATEWAY -eq 1 ]] && reclaim_port "$GW_PORT" "gateway"
  reclaim_port "$CTRL_PORT" "controller"
  [[ $WITH_VIEW -eq 1 ]] && reclaim_port "$VIEW_PORT" "view"
  echo "✓ stopped (ports free)"
  exit 0
fi

mkdir -p "$LOG_DIR" "$WORK_DIR"

# -- Python deps (install missing ones into the current interpreter) ----------
if ! python3 -c "import fastmcp, fastapi, uvicorn" >/dev/null 2>&1; then
  echo "→ installing Python deps (gateway + controller requirements)…"
  python3 -m pip install -r "$ROOT/gateway/requirements.txt" -r "$ROOT/controller/requirements.txt" \
    || die "pip install failed"
fi

# -- Web deps ------------------------------------------------------------------
if [[ $WITH_VIEW -eq 1 && ! -x "$ROOT/view/node_modules/.bin/vite" ]]; then
  echo "→ installing view deps (npm install)…"
  ( npm --prefix "$ROOT/view" install ) || die "npm install failed"
fi

# -- Env: dev token (loopback only) + shared work dir --------------------------
# The gateway refuses CRAFTER_DEV_TOKEN on non-loopback binds (see gateway/main.py).
if [[ -z "${CRAFTER_DEV_TOKEN:-}" ]]; then
  export CRAFTER_DEV_TOKEN="dev-local-token"
  echo "→ using default dev token (CRAFTER_DEV_TOKEN=dev-local-token); set your own to override"
fi
export CRAFTER_WORK_DIR="$WORK_DIR"

# -- Live desktop apps (Lane 3, optional) -------------------------------------
# Two ways to get a live window into the picker (3 · Live app window):
#
#   A. Press the per-app Launch button in the UI — the controller starts the
#      desktop binary itself (needs it on PATH or CRAFTER_DESKTOP_<APP> set,
#      see below) and registers its control channel, no restart needed.
#      pdfcraft has no TCP control channel — start it by hand, drop the PDF.
#
#   B. Start a Craft app with its control channel by hand, then export the
#      matching vars BEFORE ./start.sh so the controller picker and the
#      gateway bridge see the live window:
#   photocraft --control 7878 --control-token-file /tmp/pc.token \
#     --automation-read-root "$WORK_DIR" --automation-write-root "$WORK_DIR" &
#   export CRAFTER_BRIDGE_PHOTOCRAFT=127.0.0.1:7878
#   export CRAFTER_BRIDGE_PHOTOCRAFT_TOKEN_FILE=/tmp/pc.token
#   gridcraft --control 7979 &
#   export CRAFTER_BRIDGE_GRIDCRAFT=127.0.0.1:7979
# (pdfcraft has no TCP control channel — drop the PDF file instead.)
#
# For path A, point the controller at the desktop binaries (built with e.g.
# `cargo build --release -p photocraft` in the app source checkout).
# Precedence per app: CRAFTER_DESKTOP_<APP> (already set) → PATH →
# deploy/local-bin-paths.env (PHOTOCRAFT_DESKTOP=...) → well-known
# ~/Downloads/CRAFT/<app>-main/target/release/<app> build locations.
if [[ -f "$ROOT/deploy/local-bin-paths.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT/deploy/local-bin-paths.env"
  set +a
fi
for _app in photocraft gridcraft; do
  _var="CRAFTER_DESKTOP_$(printf '%s' "$_app" | tr '[:lower:]' '[:upper:]')"
  _alt="$(printf '%s_DESKTOP' "$_app" | tr '[:lower:]' '[:upper:]')"
  if [[ -z "${!_var:-}" ]]; then
    if have "$_app"; then
      export "$_var"="$(command -v "$_app")"
    elif [[ -n "${!_alt:-}" && -x "${!_alt}" ]]; then
      export "$_var"="${!_alt}"
    elif [[ -x "$HOME/Downloads/CRAFT/${_app}-main/target/release/$_app" ]]; then
      export "$_var"="$HOME/Downloads/CRAFT/${_app}-main/target/release/$_app"
    fi
  fi
  if [[ -n "${!_var:-}" ]]; then
    echo "→ live launch: $_app at ${!_var}"
  else
    echo "→ live launch: $_app binary not found (Launch will 502 — build it or set $_var)"
  fi
done
unset _app _var _alt

PIDS=()
CLEANING_UP=0
cleanup() {
  [[ $CLEANING_UP -eq 1 ]] && return 0
  CLEANING_UP=1
  for pid in ${PIDS[@]:-}; do
    # Kill children first (e.g. vite when launched via npm), then the parent.
    pkill -P "$pid" 2>/dev/null || true
    kill "$pid" 2>/dev/null || true
  done
  sleep 2
  for pid in ${PIDS[@]:-}; do
    # Escalate: anything still alive gets SIGKILL (npm may not forward TERM).
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
    pkill -9 -P "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup INT TERM HUP EXIT

if [[ $AUTO_CLEANUP -eq 1 ]]; then
  [[ $WITH_GATEWAY -eq 1 ]] && reclaim_port "$GW_PORT" "gateway"
  reclaim_port "$CTRL_PORT" "controller"
  [[ $WITH_VIEW -eq 1 ]] && reclaim_port "$VIEW_PORT" "view"
fi

wait_for() { # wait_for <url> <label> — up to ~30s
  local url="$1" label="$2" i
  for i in $(seq 1 60); do
    if python3 -c "import sys,urllib.request; urllib.request.urlopen(sys.argv[1], timeout=2).read()" "$url" >/dev/null 2>&1; then
      echo "✓ $label up ($url)"
      return 0
    fi
    sleep 0.5
  done
  echo "✗ $label did not respond at $url — see $LOG_DIR/${label%% *}.log" >&2
  return 1
}

# -- Gateway :8787 -------------------------------------------------------------
if [[ $WITH_GATEWAY -eq 1 ]]; then
  port_busy "$GW_PORT" && die "port $GW_PORT busy — is the gateway already running? (--gateway-port to change)"
  echo "→ starting gateway on $HOST:$GW_PORT (log: $LOG_DIR/gateway.log)…"
  python3 -m gateway.main --transport http --host "$HOST" --port "$GW_PORT" --work-dir "$WORK_DIR" \
    >"$LOG_DIR/gateway.log" 2>&1 &
  PIDS+=($!)
fi

# -- Controller :8790 ----------------------------------------------------------
port_busy "$CTRL_PORT" && die "port $CTRL_PORT busy — is the controller already running? (--controller-port to change)"
echo "→ starting controller on $HOST:$CTRL_PORT (log: $LOG_DIR/controller.log)…"
python3 -m uvicorn controller.service:app --host "$HOST" --port "$CTRL_PORT" \
  >"$LOG_DIR/controller.log" 2>&1 &
PIDS+=($!)

# -- View :8791 (vite dev, proxies /api → controller) ---------------------------
if [[ $WITH_VIEW -eq 1 ]]; then
  port_busy "$VIEW_PORT" && die "port $VIEW_PORT busy — is the view already running? (--view-port to change)"
  echo "→ starting view on $HOST:$VIEW_PORT (log: $LOG_DIR/view.log)…"
  npm run dev --prefix "$ROOT/view" -- --host "$HOST" --port "$VIEW_PORT" \
    >"$LOG_DIR/view.log" 2>&1 &
  PIDS+=($!)
fi

echo ""
wait_for "http://$HOST:$CTRL_PORT/api/health" "controller" || { tail -n 20 "$LOG_DIR/controller.log"; exit 1; }

if [[ $WITH_GATEWAY -eq 1 ]]; then
  # The MCP endpoint only answers POST/SSE, so readiness = TCP accept.
  for _ in $(seq 1 60); do port_busy "$GW_PORT" && break; sleep 0.5; done
  port_busy "$GW_PORT" \
    && echo "✓ gateway up (http://$HOST:$GW_PORT/mcp)" \
    || { echo "✗ gateway did not open port $GW_PORT — see $LOG_DIR/gateway.log" >&2; tail -n 20 "$LOG_DIR/gateway.log"; exit 1; }
fi

if [[ $WITH_VIEW -eq 1 ]]; then
  wait_for "http://$HOST:$VIEW_PORT/" "view" || { tail -n 20 "$LOG_DIR/view.log"; exit 1; }
  if [[ "$CTRL_PORT" != "8790" ]]; then
    echo "⚠ view proxies /api → 127.0.0.1:8790 (hardcoded in view/vite.config.ts),"
    echo "  but the controller runs on $CTRL_PORT — chat will show 'controller unreachable'."
    echo "  Use --controller-port 8790 or update vite.config.ts."
  fi
fi

echo ""
echo "  chat UI:    http://$HOST:$VIEW_PORT/  (setup at #/settings)"
echo "  controller: http://$HOST:$CTRL_PORT/api/health"
if [[ $WITH_GATEWAY -eq 1 ]]; then
echo "  gateway:    http://$HOST:$GW_PORT/mcp (bearer: \$CRAFTER_DEV_TOKEN)"
fi
echo ""
echo "Logs in $LOG_DIR/. Press Ctrl+C to stop everything."

if [[ $OPEN_BROWSER -eq 1 && $WITH_VIEW -eq 1 ]]; then
  if have open; then open "http://$HOST:$VIEW_PORT/" 2>/dev/null || true
  elif have xdg-open; then xdg-open "http://$HOST:$VIEW_PORT/" 2>/dev/null || true
  fi
fi

wait
