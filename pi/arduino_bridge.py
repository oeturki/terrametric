#!/usr/bin/env python3
"""
Arduino -> TerraMetric bridge (runs on the Raspberry Pi).

Reads JSON lines emitted by `arduino/arduino_bluetooth/arduino_bluetooth.ino`
over HC-05 Bluetooth Classic (bound to /dev/rfcomm0 by `rfcomm bind`) and
forwards each reading to the FastAPI ingest endpoint on the same host.

Design notes
------------
* The Arduino sketch `println`s one JSON object per line at ~5 Hz (delay 200ms).
  Keys already match backend/schemas/ingest.py::TelemetryIngest, so no payload
  translation is needed; we only tack on `bt_name` so the backend can look up
  the Device row registered in the UI and attach telemetry to the open
  recording session.
* Reconnect loop: if the serial link drops (e.g. HC-05 goes out of range, or
  `rfcomm` gets released) we retry every RETRY_SECONDS without exiting, so the
  systemd unit never has to restart us for transient link loss.
* Optional **servo on the same Bluetooth link**: set `TM_BRIDGE_CMD_SERVER=1` to
  bind `POST /servo` on 127.0.0.1 (default `TM_BRIDGE_CMD_PORT=18765`). The body
  is a line like `S90\n`, written to the open serial. Use this when the Pi has
  **no** USB serial to the Arduino: run `hardware_agent` with
  `TERRA_ARDUINO_CMD_URL=http://127.0.0.1:18765/servo` so one process owns
  ``/dev/rfcomm0``.
* Keep third-party deps minimal: only `pyserial` and `requests`. No asyncio,
  no MQTT, no Node-RED required for the happy path (stdlib `http.server` for cmd).

Configuration (env vars override defaults):
    TM_BRIDGE_PORT      serial device (default /dev/rfcomm0)
    TM_BRIDGE_BAUD      baud rate    (default 9600)
    TM_BRIDGE_API       API base     (default http://127.0.0.1:8000)
    TM_BRIDGE_BT_NAME   device name  (default Group14)  -- must match AT+NAME in the sketch
                                                            and Device.bt_name in the UI
    TM_BRIDGE_PLANT_ID  optional int — sample/plant id from Manage Samples. When set, each
                        ingest includes ``plant_id`` so threshold alerts work even with no
                        open recording session (set to the same id as the sample you control).
    TM_BRIDGE_CMD_SERVER  0/1 — POST /servo on 127.0.0.1 (default 0; set 1 for BT-only servo)
    TM_BRIDGE_CMD_PORT    port for the command server (default 18765)

Usage:
    pip install pyserial requests
    python pi/arduino_bridge.py
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional

try:
    import requests
    import serial
except ImportError as exc:  # pragma: no cover - explicit hint for the Pi user
    print(
        "[bridge] missing dependency: " + str(exc) + "\n"
        "Install with:  pip install pyserial requests",
        file=sys.stderr,
    )
    raise SystemExit(1)


PORT = os.environ.get("TM_BRIDGE_PORT", "/dev/rfcomm0")
BAUD = int(os.environ.get("TM_BRIDGE_BAUD", "9600"))
API_BASE = os.environ.get("TM_BRIDGE_API", "http://127.0.0.1:8000").rstrip("/")
BT_NAME = os.environ.get("TM_BRIDGE_BT_NAME", "Group14")
_PLANT_RAW = os.environ.get("TM_BRIDGE_PLANT_ID", "").strip()
try:
    PLANT_ID: Optional[int] = int(_PLANT_RAW) if _PLANT_RAW else None
except ValueError:
    PLANT_ID = None

INGEST_PATH = "/api/telemetry/ingest"
RETRY_SECONDS = 3
HTTP_TIMEOUT = 3
SERIAL_TIMEOUT = 2
_CMD_PORT_DEFAULT = 18765

# Only forward rows that contain at least one of these numeric keys. Guards
# against noise / partial lines ("Started\r\n" at boot, AT command echoes).
REQUIRED_ANY = ("temperature", "humidity", "light", "distance", "movement", "plant_height")

log = logging.getLogger("arduino_bridge")


def _setup_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s [bridge] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
        level=logging.INFO,
    )


def _parse_line(raw: str) -> Optional[Dict[str, Any]]:
    """Return a payload dict for valid JSON lines, else None."""
    line = raw.strip()
    if not line or not line.startswith("{") or not line.endswith("}"):
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    if not any(k in obj for k in REQUIRED_ANY):
        return None
    return obj


def _post(session: requests.Session, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    url = API_BASE + INGEST_PATH
    try:
        r = session.post(url, json=payload, timeout=HTTP_TIMEOUT)
    except requests.RequestException as e:
        log.warning("POST failed: %s", e)
        return None
    if r.status_code >= 400:
        log.warning("ingest %s -> %s %s", r.status_code, r.reason, r.text[:200])
        return None
    try:
        return r.json()
    except ValueError:
        return None


def _start_cmd_server(ser: "serial.Serial") -> Optional[tuple[HTTPServer, threading.Thread]]:
    """Localhost POST /servo → write lines to the same serial as telemetry (BT-only servo)."""
    if os.environ.get("TM_BRIDGE_CMD_SERVER", "0").strip().lower() not in (
        "1",
        "true",
        "yes",
    ):
        return None
    try:
        cmd_port = int(os.environ.get("TM_BRIDGE_CMD_PORT", str(_CMD_PORT_DEFAULT)))
    except ValueError:
        log.warning("TM_BRIDGE_CMD_PORT is not an integer, cmd server disabled")
        return None

    write_lock = threading.Lock()

    class _CmdH(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            if self.path not in ("/", "/servo"):
                self.send_error(404, "use POST /servo or POST /")
                return
            try:
                n = int(self.headers.get("Content-Length", "0") or 0)
            except ValueError:
                n = 0
            body = self.rfile.read(n) if n else b""
            if not body:
                self.send_error(400, "empty body (e.g. S90\\n)")
                return
            b = body if body.endswith(b"\n") else body + b"\n"
            try:
                with write_lock:
                    ser.write(b)
                    ser.flush()
            except OSError as e:
                self.send_error(500, str(e)[:200])
                return
            self.send_response(200)
            self.end_headers()

        def log_message(self, _format: str, *_args) -> None:  # noqa: A003
            pass

    try:
        server = HTTPServer(("127.0.0.1", cmd_port), _CmdH)  # noqa: S104 (localhost only)
    except OSError as e:
        log.warning("cmd server bind 127.0.0.1:%s failed: %s (skip)", cmd_port, e)
        return None
    t = threading.Thread(
        target=server.serve_forever,
        name="arduino-bridge-cmd",
        daemon=True,
    )
    t.start()
    log.info("cmd server: POST http://127.0.0.1:%s/servo  (e.g. body S90)", cmd_port)
    return (server, t)


def _run_once(http: requests.Session) -> None:
    """One full serial session. Returns on error so caller can retry."""
    log.info("opening %s @ %s", PORT, BAUD)
    ser = serial.Serial(PORT, BAUD, timeout=SERIAL_TIMEOUT)
    cmd: Optional[tuple[HTTPServer, threading.Thread]] = None
    try:
        cmd = _start_cmd_server(ser)
        log.info(
            "connected; forwarding to %s (bt_name=%s, plant_id=%s)",
            API_BASE + INGEST_PATH,
            BT_NAME,
            PLANT_ID,
        )
        lines_ok = 0
        lines_bad = 0
        last_log = time.time()
        while True:
            try:
                raw_bytes = ser.readline()
            except serial.SerialException as e:
                log.warning("serial read error: %s", e)
                return

            if not raw_bytes:
                # Read timeout, loop again. Useful to notice link loss without blocking forever.
                continue

            raw = raw_bytes.decode("utf-8", errors="ignore")
            payload = _parse_line(raw)
            if payload is None:
                lines_bad += 1
                continue

            payload["bt_name"] = BT_NAME
            if PLANT_ID is not None:
                payload["plant_id"] = PLANT_ID
            result = _post(http, payload)
            if result is not None:
                lines_ok += 1
                # Log a line whenever an open session latches on / detaches so the
                # operator sees what's happening without us being chatty.
                msg = result.get("message")
                if msg:
                    log.info("ingest ok (session=%s, note=%s)", result.get("session_id"), msg)

            now = time.time()
            if now - last_log >= 15:
                log.info("health: ok=%d bad=%d in last 15s", lines_ok, lines_bad)
                lines_ok = 0
                lines_bad = 0
                last_log = now
    finally:
        if cmd is not None:
            srv, _th = cmd
            try:
                srv.shutdown()
            except Exception:
                pass
            try:
                srv.server_close()
            except Exception:
                pass
        try:
            ser.close()
        except Exception:
            pass


def main() -> int:
    _setup_logging()
    if _PLANT_RAW and PLANT_ID is None:
        log.warning("TM_BRIDGE_PLANT_ID is not a valid integer, ignored")

    shutting_down = {"flag": False}

    def _sig(_signum, _frame):
        shutting_down["flag"] = True
        log.info("signal received, shutting down")

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    http = requests.Session()
    while not shutting_down["flag"]:
        try:
            _run_once(http)
        except serial.SerialException as e:
            log.warning("serial open failed: %s", e)
        except Exception:
            log.exception("unexpected error in bridge loop")
        if shutting_down["flag"]:
            break
        log.info("retrying in %ds", RETRY_SECONDS)
        for _ in range(RETRY_SECONDS):
            if shutting_down["flag"]:
                break
            time.sleep(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
