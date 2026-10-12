# CRAFTERS dev stack (Windows mirror of start.sh).
#
# Usage:  powershell -ExecutionPolicy Bypass -File .\start.ps1
# Starts gateway :8787 + controller :8790 + view :8791 (vite dev, /api → controller).
# Live desktop apps: press the per-app Launch button in the UI (needs the
#   desktop binary on PATH or CRAFTER_DESKTOP_<APP> set — auto-exported below
#   when found); pdfcraft has no TCP control channel, start it by hand.

param(
  [string]$Host = "127.0.0.1",
  [int]$GatewayPort = 8787,
  [int]$ControllerPort = 8790,
  [int]$ViewPort = 8791,
  [switch]$NoView,
  [switch]$NoGateway
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $Root ".local-run\logs"
$WorkDir = Join-Path $Root ".local-run\work"
New-Item -ItemType Directory -Force -Path $LogDir, $WorkDir | Out-Null

function Need($cmd, $what) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "$what not found ($cmd)" }
}
Need python "python"
if (-not $NoView) { Need node "node"; Need npm "npm" }

try { python -c "import fastmcp, fastapi, uvicorn" 2>$null }
catch {
  Write-Host "-> installing Python deps..."
  python -m pip install -r "$Root\gateway\requirements.txt" -r "$Root\controller\requirements.txt"
}

if ((-not $NoView) -and (-not (Test-Path "$Root\view\node_modules\.bin\vite.cmd"))) {
  Write-Host "-> installing view deps (npm install)..."
  npm --prefix "$Root\view" install
}

if (-not $env:CRAFTER_DEV_TOKEN) {
  $env:CRAFTER_DEV_TOKEN = "dev-local-token"
  Write-Host "-> using default dev token (CRAFTER_DEV_TOKEN=dev-local-token); set your own to override"
}
$env:CRAFTER_WORK_DIR = $WorkDir

# Live-launch binaries: CRAFTER_DESKTOP_<APP> > PATH > local-bin-paths.env > well-known build dirs.
$BinPathsFile = Join-Path $Root "deploy\local-bin-paths.env"
$BinPaths = @{}
if (Test-Path $BinPathsFile) {
  Get-Content $BinPathsFile | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$') { $BinPaths[$matches[1]] = $matches[2] }
  }
}
foreach ($app in @("photocraft", "gridcraft")) {
  $var = "CRAFTER_DESKTOP_" + $app.ToUpper()
  $alt = $app.ToUpper() + "_DESKTOP"
  if (-not (Get-Item "env:$var" -ErrorAction SilentlyContinue)) {
    $found = Get-Command $app -ErrorAction SilentlyContinue
    $wellKnown = Join-Path $HOME "Downloads\CRAFT\$app-main\target\release\$app"
    if ($found) { Set-Item "env:$var" $found.Source }
    elseif ($BinPaths.ContainsKey($alt) -and (Test-Path $BinPaths[$alt])) { Set-Item "env:$var" $BinPaths[$alt] }
    elseif (Test-Path "$wellKnown.exe") { Set-Item "env:$var" "$wellKnown.exe" }
    elseif (Test-Path $wellKnown) { Set-Item "env:$var" $wellKnown }
  }
  $cur = Get-Item "env:$var" -ErrorAction SilentlyContinue
  if ($cur) { Write-Host "-> live launch: $app at $($cur.Value)" }
  else { Write-Host "-> live launch: $app binary not found (Launch will 502 — build it or set $var)" }
}

$jobs = @()
try {
  if (-not $NoGateway) {
    $jobs += Start-Process python -ArgumentList "-m","gateway.main","--transport","http","--host",$Host,"--port",$GatewayPort,"--work-dir",$WorkDir `
      -WorkingDirectory $Root -RedirectStandardOutput "$LogDir\gateway.log" -RedirectStandardError "$LogDir\gateway-err.log" -PassThru
  }
  $jobs += Start-Process python -ArgumentList "-m","uvicorn","controller.service:app","--host",$Host,"--port",$ControllerPort `
    -WorkingDirectory $Root -RedirectStandardOutput "$LogDir\controller.log" -RedirectStandardError "$LogDir\controller-err.log" -PassThru
  if (-not $NoView) {
    $jobs += Start-Process npm -ArgumentList "run","dev","--prefix","$Root\view","--","--host",$Host,"--port",$ViewPort `
      -WorkingDirectory $Root -RedirectStandardOutput "$LogDir\view.log" -RedirectStandardError "$LogDir\view-err.log" -PassThru
  }

  # Wait for controller health (~30s).
  $deadline = (Get-Date).AddSeconds(30)
  while ((Get-Date) -lt $deadline) {
    try { (Invoke-WebRequest "http://${Host}:${ControllerPort}/api/health" -TimeoutSec 2 -UseBasicParsing).StatusCode; break }
    catch { Start-Sleep -Milliseconds 500 }
  }
  Write-Host ""
  Write-Host "  chat UI:    http://${Host}:${ViewPort}/  (setup at #/settings)"
  Write-Host "  controller: http://${Host}:${ControllerPort}/api/health"
  if (-not $NoGateway) { Write-Host "  gateway:    http://${Host}:${GatewayPort}/mcp (bearer: `$env:CRAFTER_DEV_TOKEN)" }
  Write-Host ""
  Write-Host "Logs in $LogDir. Press Ctrl+C to stop everything."
  Wait-Process -Id ($jobs | ForEach-Object Id)
}
finally {
  $jobs | ForEach-Object { try { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } catch {} }
}
