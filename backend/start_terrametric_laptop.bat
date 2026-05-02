@echo off
REM TerraMetric — must live in backend folder (uses %~dp0). Full UI: http://127.0.0.1:8000
REM Checklist: repo docs\laptop-smoke-test.md · Readiness: /api/health/ready
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_terrametric_laptop.ps1"
if errorlevel 1 pause
