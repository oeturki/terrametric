# TerraMetric backend on Windows — loads backend\.env (see terrametric-laptop.env.example).
# From backend folder:
#   .\start_terrametric_laptop.ps1
# Or double-click start_terrametric_laptop.bat

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
        Write-Host "[terrametric] Created .env from terrametric-laptop.local.env (gitignored)." -ForegroundColor Green
        Write-Host "            RUN AGAIN to start uvicorn." -ForegroundColor Yellow
        exit 1
    }
    elseif (Test-Path $example) {
        Copy-Item -Path $example -Destination $dotenv -Force
        Write-Host "[terrametric] Created backend\\.env from terrametric-laptop.env.example" -ForegroundColor Green
        Write-Host "            Replace REPLACE_WITH_* and match HARDWARE_PI_KEY to Pi DEVICE_KEY. Run again." -ForegroundColor Yellow
        exit 1
    }
    else {
        Write-Host "[terrametric] Missing .env — add terrametric-laptop.env.example or terrametric-laptop.local.env (gitignored)." -ForegroundColor Red
        exit 1
    }
}

$venvPy = @(Join-Path $BackendRoot "venv\Scripts\python.exe"), (Join-Path $BackendRoot ".venv\Scripts\python.exe") | Where-Object { Test-Path $_ }
$pythonExe = if ($venvPy.Count -gt 0) { $venvPy[0] } else {
    Write-Host "[terrametric] No venv\Scripts\python.exe — python -m venv venv then pip install -r requirements.txt" -ForegroundColor Yellow
    Write-Host "[terrametric] Falling back to python on PATH …" -ForegroundColor Yellow
    "python"
}

Write-Host "[terrametric] Starting API + UI — http://0.0.0.0:8000 " -ForegroundColor Cyan
Write-Host "[terrametric] Stop with Ctrl+C" -ForegroundColor DarkGray

& $pythonExe -m uvicorn main:app --host 0.0.0.0 --reload --port 8000
