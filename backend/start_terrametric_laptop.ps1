# TerraMetric backend on Windows — loads backend\.env (see terrametric-laptop.env.example).
# One command from repo:  cd backend   then   start_terrametric_laptop.bat
# Full UI + API: http://127.0.0.1:8000 — see docs/laptop-smoke-test.md
#
#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$BackendRoot = $PSScriptRoot
Set-Location $BackendRoot

$example = Join-Path $BackendRoot "terrametric-laptop.env.example"
$localBench = Join-Path $BackendRoot "terrametric-laptop.local.env"
$dotenv = Join-Path $BackendRoot ".env"

if (-not (Test-Path $dotenv)) {
    Write-Host ""
    if (Test-Path $localBench) {
        Copy-Item -Path $localBench -Destination $dotenv -Force
        Write-Host '[terrametric] Created .env from terrametric-laptop.local.env (gitignored).' -ForegroundColor Green
        Write-Host "            RUN AGAIN to start uvicorn." -ForegroundColor Yellow
        exit 1
    }
    elseif (Test-Path $example) {
        Copy-Item -Path $example -Destination $dotenv -Force
        Write-Host '[terrametric] Created backend\.env from terrametric-laptop.env.example' -ForegroundColor Green
        Write-Host "            Replace REPLACE_WITH_* and match HARDWARE_PI_KEY to Pi DEVICE_KEY. Run again." -ForegroundColor Yellow
        exit 1
    }
    else {
        Write-Host '[terrametric] Missing .env - add terrametric-laptop.env.example or terrametric-laptop.local.env (gitignored).' -ForegroundColor Red
        exit 1
    }
}

$venvRoot = Join-Path $BackendRoot "venv"
$venvPy = Join-Path $venvRoot "Scripts\python.exe"

if (-not (Test-Path $venvPy)) {
    Write-Host '[terrametric] Creating venv in backend\venv (first run only)…' -ForegroundColor Yellow
    $created = $false
    try {
        & py -3 -m venv $venvRoot
        if (Test-Path $venvPy) { $created = $true }
    } catch { }
    if (-not $created) {
        try {
            & python -m venv $venvRoot
            if (Test-Path $venvPy) { $created = $true }
        } catch { }
    }
    if (-not $created -or -not (Test-Path $venvPy)) {
        Write-Host '[terrametric] Could not create venv. Install Python 3.11+ and ensure `py -3` or `python` runs on PATH.' -ForegroundColor Red
        exit 1
    }
}

$pythonExe = $venvPy

Write-Host '[terrametric] pip install -r requirements.txt (quiet, keeps ML deps in sync)…' -ForegroundColor DarkGray
& $pythonExe -m pip install -q --disable-pip-version-check -r (Join-Path $BackendRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    Write-Host '[terrametric] pip install failed. Fix errors above, then run again.' -ForegroundColor Red
    exit 1
}

Write-Host '[terrametric] Listening on port 8000 (all interfaces).' -ForegroundColor Cyan
Write-Host '[terrametric] Open: http://127.0.0.1:8000' -ForegroundColor Green
Write-Host '[terrametric] Readiness JSON: http://127.0.0.1:8000/api/health/ready' -ForegroundColor DarkGray
Write-Host '[terrametric] Full checklist: docs/laptop-smoke-test.md (repo root)' -ForegroundColor DarkGray

$lanIp = $null
try {
  $cand = (
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
      Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
      Sort-Object InterfaceMetric |
      Select-Object -First 1
  )
  if ($cand) { $lanIp = $cand.IPAddress }
} catch { }

if ($lanIp) {
  Write-Host "[terrametric] Other devices on LAN: http://${lanIp}:8000  (firewall …)" -ForegroundColor DarkGray
} else {
  Write-Host '[terrametric] Other devices: ipconfig IPv4 … http://<ip>:8000' -ForegroundColor DarkGray
}

Write-Host '[terrametric] Stop with Ctrl+C' -ForegroundColor DarkGray

& $pythonExe -m uvicorn main:app --host 0.0.0.0 --reload --reload-delay 1 --port 8000

