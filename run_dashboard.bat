@echo off
title TerraMetric
cd /d "%~dp0backend"
echo.
echo  TerraMetric — starting API + dashboard
echo  Main UI: frontend\index.html  served at  http://127.0.0.1:8000/
echo.
python -m uvicorn main:app --host 127.0.0.1 --port 8000
if errorlevel 1 (
  echo.
  echo  If python was not found, install Python 3 and try again.
  pause
)
