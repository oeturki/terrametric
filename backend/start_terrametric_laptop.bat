@echo off
REM TerraMetric backend launcher (PowerShell wrapper)
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_terrametric_laptop.ps1"
if errorlevel 1 pause
