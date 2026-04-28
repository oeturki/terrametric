"""
Small FastAPI service that runs on the Raspberry Pi (camera + servo/ventilation).

Reachability from the laptop: same WiFi or USB Ethernet gadget. From the laptop run:
  ping <pi-ip>
  curl -s http://<pi-ip>:8765/health

Run on the Pi:
  export DEVICE_KEY='your-shared-secret'
  For Pi GPIO ventilation: export SERVO_PIN=12; sudo pigpiod  (uses pigpio API, not gpiozero)
  For Arduino over BT: export TERRA_ARDUINO_CMD_URL=http://127.0.0.1:18765/servo
  To force Pi GPIO even if TERRA_ARDUINO_CMD_URL is set: export TERRA_USE_ARDUINO_SERVO=0
  uvicorn hardware_agent:app --host 0.0.0.0 --port 8765 --app-dir pi

Install (Pi):
  sudo apt install -y python3-picamera2 python3-pil pigpio
  pip install -r pi/requirements-hardware-agent.txt
  sudo pigpiod
"""

from __future__ import annotations

import io
import os
import time
import urllib.error
import urllib.request
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

DEVICE_KEY = os.environ.get("DEVICE_KEY", "").strip()
# BCM pin for servo signal to pigpiod. 12/18 are common; avoid 5 on Pi 5.
SERVO_PIN = int(os.environ.get("SERVO_PIN", "12"))
# Pulse width in µs (edit if your horn range is off)
SERVO_PULSE_US_MIN = int(os.environ.get("SERVO_PULSE_US_MIN", "500"))
SERVO_PULSE_US_MAX = int(os.environ.get("SERVO_PULSE_US_MAX", "2500"))
# pigpiod host (default loopback; set if daemon runs elsewhere)
PIGPIO_HOST = (os.environ.get("PIGPIO_HOST") or "localhost").strip() or "localhost"
# Opt-in: drive servo on Arduino. Auto-on if TERRA_ARDUINO_CMD_URL is set (BT bridge).
# Set TERRA_USE_ARDUINO_SERVO=0 to force Pi GPIO even when the URL is in the environment.
_ard_env = os.environ.get("TERRA_USE_ARDUINO_SERVO", "").strip().lower()
_ard_url = (os.environ.get("TERRA_ARDUINO_CMD_URL") or "").strip()
if _ard_env in ("0", "false", "no"):
    USE_ARDUINO_SERVO = False
else:
    USE_ARDUINO_SERVO = _ard_env in ("1", "true", "yes") or bool(_ard_url)
ARDUINO_CMD_URL = _ard_url
ARDUINO_PORT = (os.environ.get("TERRA_ARDUINO_PORT") or "/dev/ttyACM0").strip()
ARDUINO_BAUD = int(os.environ.get("TERRA_ARDUINO_BAUD", "9600"))

app = FastAPI(title="TerraMetric Pi hardware agent", version="1.0.0")


class VentilationBody(BaseModel):
    """on=True with no fixed angle: sweep servo for visible motion. spin=False: jump to 90° only."""

    on: Optional[bool] = None
    angle: Optional[float] = Field(default=None, ge=0, le=180)
    spin: bool = True


def _require_key(x_device_key: Optional[str]) -> None:
    if not DEVICE_KEY:
        raise HTTPException(
            status_code=500,
            detail="DEVICE_KEY is not set on the Pi (set the same value as HARDWARE_PI_KEY on the laptop)",
        )
    if (x_device_key or "").strip() != DEVICE_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Device-Key")


def _capture_jpeg_bytes() -> bytes:
    """Return a JPEG using Picamera2 (Bookworm / modern Pi OS)."""
    try:
        from picamera2 import Picamera2  # type: ignore
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail="picamera2 not available. On the Pi: sudo apt install -y python3-picamera2",
        ) from e
    try:
        from PIL import Image
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail="Pillow not available. On the Pi: sudo apt install -y python3-pil",
        ) from e

    picam2 = Picamera2()
    picam2.configure(picam2.create_still_configuration())
    picam2.start()
    time.sleep(0.4)
    try:
        arr = picam2.capture_array()
    finally:
        picam2.stop()
        picam2.close()

    # Still capture is often RGB / RGBA depending on mode; convert to RGB for JPEG
    im = Image.fromarray(arr)
    if im.mode != "RGB":
        im = im.convert("RGB")
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


# --- Optional: ventilate via Arduino (USB or BT bridge) — TERRA_USE_ARDUINO_SERVO, Servo on D6 in sketch ---
_arduino_serial = None  # type: ignore[var-annotated]


def _get_arduino_serial():
    global _arduino_serial
    if _arduino_serial is not None:
        try:
            if _arduino_serial.is_open:  # type: ignore[union-attr]
                return _arduino_serial
        except Exception:
            _arduino_serial = None
    try:
        import serial  # type: ignore[import-not-found]
    except ImportError as e:
        raise HTTPException(503, detail="pyserial not installed. In the venv: pip install pyserial") from e
    try:
        _arduino_serial = serial.Serial(ARDUINO_PORT, ARDUINO_BAUD, timeout=0.2)  # type: ignore[assignment]
        time.sleep(0.15)
        return _arduino_serial
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Arduino USB not available at {ARDUINO_PORT} ({e!s}). "
                "Plug the Arduino into the Pi, check dmesg for ttyACM* / ttyUSB*, "
                "or set TERRA_ARDUINO_CMD_URL (BT bridge) or leave TERRA_USE_ARDUINO_SERVO unset and use Pi GPIO (pigpiod) only."
            ),
        ) from e


def _arduino_send_line(line: str) -> None:
    """Write one line (e.g. S90\\n or Z\\n) to the BT bridge POST or USB Arduino."""
    if ARDUINO_CMD_URL:
        data = line.encode("ascii")
        req = urllib.request.Request(
            ARDUINO_CMD_URL,
            data=data,
            method="POST",
            headers={"Content-Type": "text/plain; charset=ascii"},
        )
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                if int(resp.status) != 200:  # type: ignore[arg-type]
                    raise OSError("unexpected status from bridge")
        except urllib.error.HTTPError as e:
            raise HTTPException(
                503,
                detail=f"Arduino command bridge at {ARDUINO_CMD_URL} returned HTTP {e.code}",
            ) from e
        except urllib.error.URLError as e:
            raise HTTPException(
                503,
                detail=(
                    f"Could not reach Arduino command bridge at {ARDUINO_CMD_URL} ({e!s}). "
                    "On the Pi: run arduino_bridge.py with TM_BRIDGE_CMD_SERVER=1 and the same port as the URL path."
                ),
            ) from e
    else:
        ser = _get_arduino_serial()
        ser.write(line.encode("ascii"))
        ser.flush()
    time.sleep(0.02)


def _arduino_set_angle(deg: float) -> None:
    d = int(max(0, min(180, round(deg))))
    _arduino_send_line(f"S{d}\n")


def _arduino_detach_servos() -> None:
    """Tell the sketch to Servo.detach() — stops PWM until next S angle (Ventilation OFF)."""
    _arduino_send_line("Z\n")


def _arduino_vent_path() -> str:
    return ARDUINO_CMD_URL if ARDUINO_CMD_URL else f"USB {ARDUINO_PORT}"


def _arduino_spin_sweep() -> tuple[float, str]:
    pattern = [0, 20, 40, 60, 80, 100, 120, 140, 160, 180, 160, 140, 120, 100, 80, 60, 40, 20, 90]
    step_s = 0.045
    for a in pattern:
        _arduino_set_angle(float(a))
        time.sleep(step_s)
    return 90.0, f"Arduino sweep ({len(pattern)} steps), rest 90° ({_arduino_vent_path()})"


def _apply_ventilation_arduino(body: VentilationBody) -> tuple[float, str]:
    path = _arduino_vent_path()
    if body.angle is not None:
        ang = max(0.0, min(180.0, float(body.angle)))
        _arduino_set_angle(ang)
        return ang, f"Arduino servo {ang}° ({path})"
    if body.on is False:
        _arduino_detach_servos()
        return 0.0, f"Arduino servo detached / PWM off ({path})"
    if body.on is True and body.spin:
        return _arduino_spin_sweep()
    if body.on is True and not body.spin:
        _arduino_set_angle(90.0)
        return 90.0, f"Arduino servo 90° (no sweep) ({path})"
    if body.spin:
        return _arduino_spin_sweep()
    _arduino_set_angle(90.0)
    return 90.0, f"Arduino servo 90° ({path})"


_pig: Optional[object] = None


def _deg_to_pulse_us(deg: float) -> int:
    d = max(0.0, min(180.0, float(deg)))
    return int(
        SERVO_PULSE_US_MIN
        + (SERVO_PULSE_US_MAX - SERVO_PULSE_US_MIN) * (d / 180.0)
    )


def _get_pigpio() -> "object":
    """Connected pigpio.pi() — Pi GPIO ventilation uses this only (no gpiozero)."""
    global _pig
    if _pig is not None:
        try:
            if getattr(_pig, "connected", True):  # type: ignore[union-attr]
                return _pig
        except Exception:
            _pig = None
    try:
        import pigpio  # type: ignore[import-not-found]
    except ImportError as e:
        raise HTTPException(
            503,
            detail="`pigpio` Python package not installed. In the agent venv: pip install pigpio",
        ) from e
    pi = pigpio.pi(PIGPIO_HOST)  # type: ignore[call-arg]
    if not pi.connected:  # type: ignore[union-attr]
        raise HTTPException(
            503,
            detail=(
                f"pigpiod is not running or not reachable at {PIGPIO_HOST!r} (port 8888). "
                "On the Pi: sudo apt install -y pigpio && sudo pigpiod. "
                "Or use the Arduino: export TERRA_ARDUINO_CMD_URL=... and run arduino_bridge with TM_BRIDGE_CMD_SERVER=1."
            ),
        )
    _pig = pi
    return pi


def _pi_gpio_set_angle(deg: float) -> None:
    pi = _get_pigpio()
    w = _deg_to_pulse_us(deg)
    # pigpio handles 50Hz servo mode on the pin
    pi.set_servo_pulsewidth(SERVO_PIN, w)  # type: ignore[union-attr]
    time.sleep(0.02)


def _pi_gpio_servo_off() -> None:
    """Release pin (0 = no pulses)."""
    pi = _get_pigpio()
    pi.set_servo_pulsewidth(SERVO_PIN, 0)  # type: ignore[union-attr]
    time.sleep(0.02)


def _pi_gpio_spin_sweep() -> tuple[float, str]:
    pattern = [0, 20, 40, 60, 80, 100, 120, 140, 160, 180, 160, 140, 120, 100, 80, 60, 40, 20, 90]
    step_s = 0.045
    for a in pattern:
        _pi_gpio_set_angle(float(a))
        time.sleep(step_s)
    return 90.0, f"Pi pigpio sweep on GPIO{SERVO_PIN} ({len(pattern)} steps), rest 90°"


def _apply_ventilation_pi_pigpio(body: VentilationBody) -> tuple[float, str]:
    if body.angle is not None:
        ang = max(0.0, min(180.0, float(body.angle)))
        _pi_gpio_set_angle(ang)
        return ang, f"Pi pigpio GPIO{SERVO_PIN} → {ang}°"
    if body.on is False:
        _pi_gpio_servo_off()
        return 0.0, f"Pi pigpio GPIO{SERVO_PIN} servo off (pulse 0)"
    if body.on is True and body.spin:
        return _pi_gpio_spin_sweep()
    if body.on is True and not body.spin:
        _pi_gpio_set_angle(90.0)
        return 90.0, f"Pi pigpio GPIO{SERVO_PIN} 90° (no sweep)"
    if body.spin:
        return _pi_gpio_spin_sweep()
    _pi_gpio_set_angle(90.0)
    return 90.0, f"Pi pigpio GPIO{SERVO_PIN} 90°"


def _apply_ventilation(body: VentilationBody) -> tuple[float, str]:
    if USE_ARDUINO_SERVO:
        return _apply_ventilation_arduino(body)
    return _apply_ventilation_pi_pigpio(body)


@app.get("/health")
def health():
    """Public: use from the laptop to verify `ping` + TCP (no key required)."""
    m: dict = {"status": "ok", "service": "terrametric_hardware_agent"}
    if USE_ARDUINO_SERVO:
        if ARDUINO_CMD_URL:
            m["ventilation"] = "arduino_bluetooth"
            m["arduino_cmd_url"] = ARDUINO_CMD_URL
        else:
            m["ventilation"] = "arduino_usb"
            m["arduino_port"] = ARDUINO_PORT
    else:
        m["ventilation"] = "pi_pigpio"
        m["servo_bcm"] = SERVO_PIN
        m["pigpio_host"] = PIGPIO_HOST
    return m


@app.post("/camera/capture")
def camera_capture(x_device_key: Optional[str] = Header(default=None, alias="X-Device-Key")):
    _require_key(x_device_key)
    try:
        jpeg = _capture_jpeg_bytes()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Capture failed: {e!s}") from e
    return Response(content=jpeg, media_type="image/jpeg")


@app.post("/ventilation")
def ventilation(
    body: VentilationBody,
    x_device_key: Optional[str] = Header(default=None, alias="X-Device-Key"),
):
    _require_key(x_device_key)
    try:
        ang, msg = _apply_ventilation(body)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ventilation failed: {e!s}") from e
    return {"ok": True, "angle": ang, "detail": msg}
