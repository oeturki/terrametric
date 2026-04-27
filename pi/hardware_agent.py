"""
Small FastAPI service that runs on the Raspberry Pi (camera + servo/ventilation).

Reachability from the laptop: same WiFi or USB Ethernet gadget. From the laptop run:
  ping <pi-ip>
  curl -s http://<pi-ip>:8765/health

Run (on the Pi):
  export DEVICE_KEY='your-shared-secret'
  # --- Ventilation: Pi GPIO (default) ---
  # export SERVO_PIN=5
  # export USE_PIGPIO=0
  # --- Ventilation: Arduino on USB (opt-in; servo on Arduino D6) ---
  # export TERRA_USE_ARDUINO_SERVO=1
  # export TERRA_ARDUINO_PORT=/dev/ttyACM0
  # --- Or Arduino only on Bluetooth (same link as arduino_bridge.py): ---
  # export TERRA_USE_ARDUINO_SERVO=1
  # export TERRA_ARDUINO_CMD_URL=http://127.0.0.1:18765/servo
  # On the Pi: TM_BRIDGE_CMD_SERVER=1 when running arduino_bridge.py
  # pip install pyserial
  uvicorn hardware_agent:app --host 0.0.0.0 --port 8765

Install (Pi):
  sudo apt install -y python3-picamera2 python3-pil python3-gpiozero
  pip install fastapi "uvicorn[standard]" python-multipart pyserial
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
# BCM pin for servo *signal* (default 5 for typical "D5" / GPIO5 wiring; override if your HAT maps D5 elsewhere).
SERVO_PIN = int(os.environ.get("SERVO_PIN", "5"))
USE_PIGPIO = os.environ.get("USE_PIGPIO", "").strip().lower() in ("1", "true", "yes")
# Opt-in: drive servo on Arduino (USB serial S###) instead of Pi GPIO — no GPIO PWM on the Pi in this mode.
USE_ARDUINO_SERVO = os.environ.get("TERRA_USE_ARDUINO_SERVO", "").strip().lower() in ("1", "true", "yes")
# When set, servo lines are POSTed here (e.g. arduino_bridge BT cmd server) instead of opening USB serial.
ARDUINO_CMD_URL = (os.environ.get("TERRA_ARDUINO_CMD_URL") or "").strip()
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
                "or use TERRA_ARDUINO_CMD_URL (arduino_bridge on Bluetooth) or set TERRA_USE_ARDUINO_SERVO=0 for Pi GPIO only."
            ),
        ) from e


def _arduino_set_angle(deg: float) -> None:
    d = int(max(0, min(180, round(deg))))
    line = f"S{d}\n"
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
        _arduino_set_angle(0.0)
        return 0.0, f"Arduino servo 0° ({path})"
    if body.on is True and body.spin:
        return _arduino_spin_sweep()
    if body.on is True and not body.spin:
        _arduino_set_angle(90.0)
        return 90.0, f"Arduino servo 90° (no sweep) ({path})"
    if body.spin:
        return _arduino_spin_sweep()
    _arduino_set_angle(90.0)
    return 90.0, f"Arduino servo 90° ({path})"


_servo = None
_pin_factory_tried: Optional[str] = None


def _set_pigpio_factory() -> None:
    """Software PWM via pigpiod — allows more pins if `sudo pigpiod` is running."""
    from gpiozero import Device
    from gpiozero.pins.pigpio import PiGPIOFactory

    Device.pin_factory = PiGPIOFactory()


def _make_angular_servo():
    from gpiozero import AngularServo

    return AngularServo(SERVO_PIN, min_angle=0, max_angle=180)


def _ensure_servo() -> "object":
    global _servo, _pin_factory_tried
    if _servo is not None:
        return _servo
    try:
        from gpiozero import AngularServo  # noqa: F401
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail="gpiozero not available. On the Pi: sudo apt install -y python3-gpiozero",
        ) from e

    if USE_PIGPIO:
        try:
            _set_pigpio_factory()
            _pin_factory_tried = "pigpio"
        except Exception as e:
            raise HTTPException(
                status_code=503,
                detail=f"USE_PIGPIO=1 but pigpio failed: {e!s}. Run: sudo apt install -y pigpio && sudo pigpiod",
            ) from e
        try:
            _servo = _make_angular_servo()
        except Exception as e:
            raise HTTPException(
                status_code=503,
                detail=f"Servo on GPIO{SERVO_PIN} failed (pigpio): {e!s}",
            ) from e
        return _servo

    try:
        _servo = _make_angular_servo()
        _pin_factory_tried = "default"
    except Exception as e0:
        err0 = str(e0)
        if "PWM" not in err0 and "pwm" not in err0.lower():
            raise HTTPException(
                status_code=503,
                detail=f"Could not open servo on GPIO{SERVO_PIN}: {err0}",
            ) from e0
        try:
            _set_pigpio_factory()
            _pin_factory_tried = "pigpio (auto)"
            _servo = _make_angular_servo()
        except Exception as e1:
            extra = (
                " In the venv run: pip install pigpio. Also: sudo apt install -y pigpio && sudo pigpiod (daemon must be running)."
            )
            if "pigpio" in str(e1).lower() and "module" in str(e1).lower():
                extra = " Install the *Python* client: `pip install pigpio` (same venv as uvicorn), then `sudo apt install -y pigpio && sudo pigpiod`."
            raise HTTPException(
                status_code=503,
                detail=(
                    f"PWM not available on GPIO{SERVO_PIN} ({err0}). "
                    f"Option A: move servo signal to BCM 12 or 13, `export SERVO_PIN=12` (or 13), restart the agent. "
                    f"Option B: use pigpiod for software PWM on more pins —{extra} Auto-fallback error: {e1!s}"
                ),
            ) from e0

    return _servo


def _spin_sweep(srv: object) -> tuple[float, str]:
    """
    Standard positional servos: step through angles so the horn visibly sweeps
    (not a continuous 'motor spin'—that needs a different servo type and API).
    """
    pattern = [0, 20, 40, 60, 80, 100, 120, 140, 160, 180, 160, 140, 120, 100, 80, 60, 40, 20, 90]
    step_s = 0.045
    for a in pattern:
        srv.angle = float(a)  # type: ignore[union-attr]
        time.sleep(step_s)
    return 90.0, f"Sweep on GPIO{SERVO_PIN} ({len(pattern)} steps), rest 90° ({_pin_factory_tried or 'default'})"


def _apply_ventilation(body: VentilationBody) -> tuple[float, str]:
    if USE_ARDUINO_SERVO:
        return _apply_ventilation_arduino(body)
    srv = _ensure_servo()

    if body.angle is not None:
        ang = max(0.0, min(180.0, float(body.angle)))
        srv.angle = ang
        return ang, f"Servo on GPIO{SERVO_PIN} set to {ang}°"

    if body.on is False:
        srv.angle = 0.0
        return 0.0, f"Servo on GPIO{SERVO_PIN} set to 0°"

    # on is True or omitted (treat as vent on)
    if body.on is True and body.spin:
        return _spin_sweep(srv)
    if body.on is True and not body.spin:
        srv.angle = 90.0
        return 90.0, f"Servo on GPIO{SERVO_PIN} set to 90° (no sweep)"

    # Empty body or {}: same as a spin for a satisfying click
    if body.spin:
        return _spin_sweep(srv)
    srv.angle = 90.0
    return 90.0, f"Servo on GPIO{SERVO_PIN} set to 90°"


@app.get("/health")
def health():
    """Public: use from the laptop to verify `ping` + TCP (no key required)."""
    m: dict = {"status": "ok", "service": "terrametric_hardware_agent"}
    m["ventilation"] = "pi_gpio"
    if USE_ARDUINO_SERVO:
        if ARDUINO_CMD_URL:
            m["ventilation"] = "arduino_bluetooth"
            m["arduino_cmd_url"] = ARDUINO_CMD_URL
        else:
            m["ventilation"] = "arduino_usb"
            m["arduino_port"] = ARDUINO_PORT
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
