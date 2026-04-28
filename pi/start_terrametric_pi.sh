#!/usr/bin/env bash
# TerraMetric Pi — one-shot: arduino_bridge (BT + ingest) + hardware_agent (camera + ventilation).
#
# Prerequisites: same directory as arduino_bridge.py and hardware_agent.py (or set TERRA_PI_DIR).
#   cp terrametric-pi.env.example .env
#   nano .env
#   chmod +x start_terrametric_pi.sh
#   ./start_terrametric_pi.sh
#
# Stop: Ctrl+C (stops both processes).

set -euo pipefail

DIR="${TERRA_PI_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
cd "$DIR"

if [[ -f "$DIR/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$DIR/.env"
  set +a
elif [[ -f "$DIR/terrametric-pi.local.env" ]]; then
  echo "[terrametric-pi] Using terrametric-pi.local.env (IPs/MAC kept out of git; optional symlink to .env)" >&2
  set -a
  # shellcheck source=/dev/null
  source "$DIR/terrametric-pi.local.env"
  set +a
else
  echo "[terrametric-pi] No $DIR/.env — copy terrametric-pi.env.example to .env and edit (or maintain terrametric-pi.local.env)." >&2
  exit 1
fi

if [[ -z "${DEVICE_KEY:-}" ]]; then
  echo "[terrametric-pi] DEVICE_KEY is empty in .env (must match HARDWARE_PI_KEY on laptop)." >&2
  exit 1
fi

PYTHON="${TERRA_PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
  if [[ -x "$DIR/.venv/bin/python3" ]]; then
    PYTHON="$DIR/.venv/bin/python3"
  else
    PYTHON="python3"
  fi
fi

for f in arduino_bridge.py hardware_agent.py; do
  if [[ ! -f "$DIR/$f" ]]; then
    echo "[terrametric-pi] Missing $DIR/$f" >&2
    exit 1
  fi
done

# Drop any stale BlueZ session to the HC-05 so RFCOMM can open (fixes Errno 16 "Device or resource busy").
if [[ -n "${TM_BRIDGE_BT_MAC:-}" ]] && command -v bluetoothctl >/dev/null 2>&1; then
  _mac="${TM_BRIDGE_BT_MAC//-/:}"
  echo "[terrametric-pi] bluetoothctl disconnect $_mac (frees SPP; errors OK) ..." >&2
  bluetoothctl disconnect "$_mac" 2>/dev/null || true
  sleep 1
fi

cleanup() {
  if [[ -n "${BRIDGE_PID:-}" ]] && kill -0 "$BRIDGE_PID" 2>/dev/null; then
    kill "$BRIDGE_PID" 2>/dev/null || true
    wait "$BRIDGE_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "[terrametric-pi] starting arduino_bridge ($PYTHON)..."
"$PYTHON" "$DIR/arduino_bridge.py" &
BRIDGE_PID=$!
sleep 1
if ! kill -0 "$BRIDGE_PID" 2>/dev/null; then
  echo "[terrametric-pi] arduino_bridge exited immediately — check .env and Bluetooth." >&2
  exit 1
fi

echo "[terrametric-pi] starting hardware_agent on 0.0.0.0:8765 (Ctrl+C stops both)..."
export DEVICE_KEY
export TERRA_ARDUINO_CMD_URL="${TERRA_ARDUINO_CMD_URL:-}"
export TERRA_USE_ARDUINO_SERVO="${TERRA_USE_ARDUINO_SERVO:-}"
export SERVO_PIN="${SERVO_PIN:-12}"
export PIGPIO_HOST="${PIGPIO_HOST:-localhost}"

exec "$PYTHON" -m uvicorn hardware_agent:app --host 0.0.0.0 --port 8765 --app-dir "$DIR"
