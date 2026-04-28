#!/usr/bin/env python3
"""
Arduino -> TerraMetric bridge (runs on the Raspberry Pi).

Reads JSON lines emitted by `arduino/arduino_bluetooth/arduino_bluetooth.ino`
over HC-05 Bluetooth Classic — either a serial device (e.g. ``/dev/rfcomm0``)
or a direct RFCOMM socket when ``TM_BRIDGE_BT_MAC`` is set — and forwards each
reading to the FastAPI ingest endpoint on the same host.

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
* Optional RFCOMM without a tty device — set ``TM_BRIDGE_BT_MAC`` (e.g. ``AA:BB:CC:DD:EE:FF``).
  Uses the Linux RFCOMM socket API (stdlib ``socket``); no ``rfcomm bind`` required.
  Optional ``TM_BRIDGE_RFCOMM_CHANNEL`` (default 1) if the module is not on channel 1.
* Keep third-party deps minimal when using serial device: ``pyserial`` + ``requests``. When
  ``TM_BRIDGE_BT_MAC`` is set, ``requests`` still required; pyserial is not used for the link.

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
    TM_BRIDGE_BT_MAC      optional — HC-05 MAC ; use RFCOMM socket (no /dev/rfcomm0).
    TM_BRIDGE_RFCOMM_CHANNEL  SPP channel (default 1)

Usage:
    pip install requests
    # serial device path (default /dev/rfcomm0):
    pip install pyserial
    python pi/arduino_bridge.py

    RFCOMM by MAC (no /dev/rfcomm*; pair & trust the HC-05 first):
    export TM_BRIDGE_BT_MAC=AA:BB:CC:DD:EE:FF
    python pi/arduino_bridge.py
"""

from __future__ import annotations

import json
import logging
import os
import signal
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional

try:
    import requests
except ImportError as exc:
    print(
        "[bridge] missing dependency: " + str(exc) + "\n"
        "Install with:  pip install requests",
        file=sys.stderr,
    )
    raise SystemExit(1)

try:
    import serial  # noqa: F401 — only needed when TM_BRIDGE_BT_MAC is unset
except ImportError:
    serial = None  # type: ignore[assignment]


PORT = os.environ.get("TM_BRIDGE_PORT", "/dev/rfcomm0")
BAUD = int(os.environ.get("TM_BRIDGE_BAUD", "9600"))
BT_MAC_RAW = (os.environ.get("TM_BRIDGE_BT_MAC") or "").strip()
try:
    RFCOMM_CHANNEL = int(os.environ.get("TM_BRIDGE_RFCOMM_CHANNEL", "1"))
except ValueError:
    RFCOMM_CHANNEL = 1
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

REQUIRED_ANY = ("temperature", "humidity", "light", "distance", "movement", "plant_height")

log = logging.getLogger("arduino_bridge")


class _SocketLineTransport:
    """RFCOMM stream with readline() compatible with bridge loop (newline-delimited JSON)."""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._buf = bytearray()

    def readline(self) -> bytes:
        while True:
            nl = self._buf.find(b"\n")
            if nl >= 0:
                line = bytes(self._buf[: nl + 1])
                del self._buf[: nl + 1]
                return line
            try:
                self._sock.settimeout(SERIAL_TIMEOUT)
                chunk = self._sock.recv(4096)
            except socket.timeout:
                return b""
            except OSError as e:
                raise ConnectionError(str(e)) from e
            if not chunk:
                raise ConnectionError("RFCOMM connection closed")
            self._buf.extend(chunk)

    def write(self, data: bytes) -> None:
        self._sock.sendall(data)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


def _open_transport() -> Any:
    """Serial port *or* Linux RFCOMM socket when TM_BRIDGE_BT_MAC is set."""
    if BT_MAC_RAW:
        mac = BT_MAC_RAW.upper().replace("-", ":")
        if mac.count(":") != 5:
            raise ValueError(
                f"TM_BRIDGE_BT_MAC must look like AA:BB:CC:DD:EE:FF, got {BT_MAC_RAW!r}"
            )
        if not hasattr(socket, "AF_BLUETOOTH"):
            raise RuntimeError(
                "socket.AF_BLUETOOTH is not available on this system. "
                "Use TM_BRIDGE_PORT=/dev/rfcomm0 with pyserial after rfcomm bind, "
                "or run on Linux (e.g. Raspberry Pi OS)."
            )
        log.info(
            "RFCOMM socket connect %s channel %s (no /dev/rfcomm*)",
            mac,
            RFCOMM_CHANNEL,
        )
        s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        try:
            s.connect((mac, RFCOMM_CHANNEL))
        except OSError as e:
            s.close()
            raise RuntimeError(f"RFCOMM connect failed: {e}") from e
        return _SocketLineTransport(s)
    if serial is None:
        raise RuntimeError(
            "pyserial is not installed but TM_BRIDGE_BT_MAC is unset. "
            "Run: pip install pyserial"
        )
    log.info("opening serial %s @ %s", PORT, BAUD)
    return serial.Serial(PORT, BAUD, timeout=SERIAL_TIMEOUT)


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


def _start_cmd_server(transp: Any) -> Optional[tuple[HTTPServer, threading.Thread]]:
    """Localhost POST /servo → write lines to the same transport as telemetry (BT-only servo)."""
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
                    transp.write(b)
                    transp.flush()
            except OSError as e:
                self.send_error(500, str(e)[:200])
                return
            try:
                preview = b.decode("ascii", errors="replace").strip().replace("\n", "\\n")
                log.info("cmd -> HC-05 link: %s", preview[:80])
            except Exception:
                pass
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
    """One transport session. Returns on error so caller can retry."""
    try:
        transp = _open_transport()
    except (RuntimeError, ValueError) as e:
        log.warning("open transport failed: %s", e)
        return
    cmd: Optional[tuple[HTTPServer, threading.Thread]] = None
    try:
        cmd = _start_cmd_server(transp)
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
                raw_bytes = transp.readline()
            except Exception as e:
                if serial is not None and isinstance(e, serial.SerialException):
                    log.warning("serial read error: %s", e)
                    return
                if isinstance(e, (ConnectionError, OSError, BrokenPipeError)):
                    log.warning("transport read error: %s", e)
                    return
                raise

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
            transp.close()
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
        except Exception as e:
            if serial is not None and isinstance(e, serial.SerialException):
                log.warning("serial failed: %s", e)
            else:
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
