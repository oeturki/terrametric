"""
Small FastAPI service that runs on the Raspberry Pi (camera + servo/ventilation).

Reachability from the laptop: same WiFi or USB Ethernet gadget. From the laptop run:
  ping <pi-ip>
  curl -s http://<pi-ip>:8765/health

Run (on the Pi):
  export DEVICE_KEY='your-shared-secret'
  # SERVO_PIN = Broadcom (BCM) number of the *signal* wire (not the 40-pin physical index).
  # Board silkscreen "D5" / Arduino-style "D5" is often GPIO5 (BCM) on Pi shields — use 5, or check your HAT's pinout.
  # Standard 3-wire *analog* (hobby) servos: GND, +5V, signal — what AngularServo drives (50 Hz PWM), not a raw analog voltage in.
  export SERVO_PIN=5
  # If PWM fails on that pin, try: export SERVO_PIN=12, move wire, OR: sudo apt install -y pigpio && sudo pigpiod
  # Optional: export USE_PIGPIO=1
  uvicorn hardware_agent:app --host 0.0.0.0 --port 8765

Install (Pi):
  sudo apt install -y python3-picamera2 python3-pil python3-gpiozero
  pip install fastapi "uvicorn[standard]" python-multipart
"""

from __future__ import annotations

import io
import os
import time
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

DEVICE_KEY = os.environ.get("DEVICE_KEY", "").strip()
# BCM pin for servo *signal* (default 5 for typical "D5" / GPIO5 wiring; override if your HAT maps D5 elsewhere).
SERVO_PIN = int(os.environ.get("SERVO_PIN", "5"))
USE_PIGPIO = os.environ.get("USE_PIGPIO", "").strip().lower() in ("1", "true", "yes")

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
    return {"status": "ok", "service": "terrametric_hardware_agent"}


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
