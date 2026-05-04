"""
Dummy telemetry engine (Phase 2 of the GMO research design).

Two responsibilities, kept in one module so they share the same generator
profiles and stay deterministic per (session_id, scenario):

1. ``ScenarioProfile`` — pure functions that produce a single synthetic
   reading for a given timestamp. Used both for the live streaming loop and
   for the historical backfill endpoint, so the dataset is internally
   consistent regardless of which path created it.

2. ``StreamSupervisor`` — an asyncio supervisor that owns one task per
   active recording session, ticks every ``interval_sec`` seconds, and
   inserts a Telemetry row attached to that session's plant. Cancellation
   is cooperative (asyncio.Task.cancel) and idempotent so the same session
   can be stopped safely twice.

Design notes:
* The supervisor uses its own DB session per tick (via ``SessionLocal``),
  not a request-scoped one — request sessions die when the request ends.
* The simulator never directly writes telemetry. It always goes through
  ``store_telemetry_row`` so plant_id/device-touch/audit logic stays in
  one place (telemetry_service).
* Scenarios deliberately produce values that **breach** the Control
  Variables thresholds so the anomaly detectors actually fire when we
  wire them in Phase 4.
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, Optional

from database import SessionLocal
from models.session import RecordingSession
from services.telemetry_service import store_telemetry_row

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Pure generator profiles
# ---------------------------------------------------------------------------

@dataclass
class GeneratedReading:
    """One synthetic snapshot — matches the keyword args of store_telemetry_row.

    ``temperature`` / ``humidity`` / ``light`` may be None to exercise missing-channel
    paths (dummy stream); movement/height stay populated for realism.
    """

    timestamp: datetime
    temperature: Optional[float]
    humidity: Optional[float]
    light: Optional[float]
    movement: bool
    distance: float
    plant_height: float


@dataclass
class ScenarioContext:
    """Per-stream state passed to every reading generator so scenarios can
    reference age-since-start (drift, drought ramp, heat spike windows)."""

    started_at: datetime
    base_height_cm: float = 5.0  # seedling baseline
    rng: random.Random = None  # type: ignore[assignment]
    # Nominal seconds between inserts (streaming + backfill).
    stream_interval_sec: float = 60.0
    # Rows already persisted before the reading currently being synthesized (streaming + backfill).
    successful_inserts_prior: int = 0
    # packet_loss streaming: countdown of insert skips → dropout gaps
    packet_loss_skip_remaining: int = 0

    def __post_init__(self):
        if self.rng is None:
            # Deterministic per-run; if you want fully random, swap to random.Random()
            self.rng = random.Random(0xA1B2C3)

    def age_minutes(self, now: datetime) -> float:
        return max(0.0, (now - self.started_at).total_seconds() / 60.0)


def _approx_reading_index(ctx: ScenarioContext, now: datetime) -> int:
    """Legacy wall-clock index (backfill pacing); prefer successful_inserts_prior for stream-aligned pulses."""

    step = max(0.2, float(ctx.stream_interval_sec or 60.0))
    elapsed = max(0.0, (now - ctx.started_at).total_seconds())
    return int(elapsed // step)


def _incoming_insert_ordinal(ctx: ScenarioContext) -> int:
    """1-based sequence number for the telemetry row currently being formed (prior rows already stored)."""

    return int(ctx.successful_inserts_prior) + 1


# Dropout learns median gap over DROPOUT_BASELINE_READINGS from *stored* timestamps only —
# defer packet bursts until baseline is sane, then skip enough ticks that gap_ratio > multiplier (default 3).
_PACKET_LOSS_WARMUP_STORES = 35
_PACKET_LOSS_BURST_SKIP_TICKS = 14
_PACKET_LOSS_BURST_EVERY_INSERTS = 90


def _baseline(now: datetime, ctx: ScenarioContext) -> GeneratedReading:
    """
    Healthy-chamber profile (used by every scenario as the starting point).

    * Temperature: sine peaking ~14:00 (23 +/- 3 C)
    * Light: sine 06:00-18:00, dark at night
    * Humidity: slow drift around 50% +/- 5
    * Movement: small chance, more likely during the day
    * Plant height: monotonic linear growth
    """
    h = now.hour + now.minute / 60.0

    temp = 23.0 + 3.0 * math.sin(2 * math.pi * (h - 6) / 24.0)
    light = max(0.0, 600.0 * math.sin(math.pi * (h - 6) / 12.0))
    hum = 50.0 + 5.0 * math.sin(2 * math.pi * (h - 12) / 24.0)
    move_prob = 0.07 if 7 <= h <= 19 else 0.01
    movement = ctx.rng.random() < move_prob

    age = ctx.age_minutes(now)
    height = ctx.base_height_cm + 0.005 * age  # 0.005 cm/min ~= 7.2 cm/day max
    distance = max(2.0, 35.0 - height)  # ultrasonic head 35 cm above the tray

    # Small gaussian noise so curves never look perfectly synthetic.
    temp  += ctx.rng.gauss(0, 0.08)
    hum   += ctx.rng.gauss(0, 0.4)
    light += ctx.rng.gauss(0, 4.0)

    return GeneratedReading(
        timestamp=now,
        temperature=round(temp, 2),
        humidity=round(max(0.0, min(100.0, hum)), 2),
        light=round(max(0.0, light), 1),
        movement=movement,
        distance=round(distance, 1),
        plant_height=round(height, 2),
    )


def _heat_spike(now: datetime, ctx: ScenarioContext) -> GeneratedReading:
    """Sharp periodic temperature pulses aligned to inserts so spikes see a calm prior window."""
    r = _baseline(now, ctx)
    n = _incoming_insert_ordinal(ctx)
    if n >= 6 and n % 8 == 0 and r.temperature is not None:
        r.temperature = round(float(r.temperature) + 14.0, 2)
    return r


def _drought(now: datetime, ctx: ScenarioContext) -> GeneratedReading:
    """Linear humidity decay 60 -> 25 across the recording window."""
    r = _baseline(now, ctx)
    # Reach 25% at age=480 min (8 h); clamp afterwards
    age = ctx.age_minutes(now)
    target = max(25.0, 60.0 - (60.0 - 25.0) * (age / 480.0))
    r.humidity = round(target + ctx.rng.gauss(0, 0.5), 2)
    return r


def _cold_night(now: datetime, ctx: ScenarioContext) -> GeneratedReading:
    """Push temperature -5 C during dark hours to simulate heater failure."""
    r = _baseline(now, ctx)
    if r.light is not None and float(r.light) < 50.0 and r.temperature is not None:
        r.temperature = round(float(r.temperature) - 5.0, 2)
    return r


def _sensor_drift(now: datetime, ctx: ScenarioContext) -> GeneratedReading:
    """Linear creep ~0.06 °C per stored synthetic row (FR10 drift vs reading index)."""
    r = _baseline(now, ctx)
    idx = ctx.successful_inserts_prior
    if r.temperature is not None:
        r.temperature = round(float(r.temperature) + 0.06 * idx, 2)
    return r


def _temp_spike_random(now: datetime, ctx: ScenarioContext) -> GeneratedReading:
    """Frequent-but-rare positive temperature spikes vs steady prior window."""
    r = _baseline(now, ctx)
    if r.temperature is not None and ctx.rng.random() < 0.12:
        r.temperature = round(float(r.temperature) + ctx.rng.uniform(11.5, 17.5), 2)
    return r


def _light_spike_burst(now: datetime, ctx: ScenarioContext) -> GeneratedReading:
    """Large light outliers on periodic inserts + modest RNG — tuned for FR10 spike on light."""

    r = _baseline(now, ctx)
    n = _incoming_insert_ordinal(ctx)
    spike = False
    if n >= 7 and (n % 6 == 0 or n % 11 == 0):
        spike = True
    if not spike and n >= 7 and ctx.rng.random() < 0.25:
        spike = True
    if spike and r.light is not None:
        r.light = round(min(1023.0, float(r.light) + ctx.rng.uniform(420.0, 580.0)), 1)
    return r


def _humidity_noise_storm(now: datetime, ctx: ScenarioContext) -> GeneratedReading:
    """Aggressive RH jitter around nominal → clears noise WARN/CRITICAL over short windows."""
    r = _baseline(now, ctx)
    if r.humidity is not None:
        r.humidity = round(max(0.0, min(100.0, float(r.humidity) + ctx.rng.gauss(0.0, 11.5))), 2)
    return r


def _drift_ramp_fast(now: datetime, ctx: ScenarioContext) -> GeneratedReading:
    """Steep additive ramp ~0.14 °C per stored row atop baseline diurnal."""

    r = _baseline(now, ctx)
    idx = ctx.successful_inserts_prior
    if r.temperature is not None:
        r.temperature = round(float(r.temperature) + 0.14 * idx, 2)
    return r


def _missing_temp_readings(now: datetime, ctx: ScenarioContext) -> GeneratedReading:
    """Intermittent DHT-style failures: humidity/light sane, temperature absent."""
    r = _baseline(now, ctx)
    if ctx.rng.random() < 0.14:
        r.temperature = None
    return r


def _packet_loss_baseline(now: datetime, ctx: ScenarioContext) -> GeneratedReading:
    """Same healthy profile; timestamps gaps for dropout come from skipped inserts in the supervisor."""
    return _baseline(now, ctx)


SCENARIOS: Dict[str, Callable[[datetime, ScenarioContext], GeneratedReading]] = {
    "stable": _baseline,
    "heat_spike": _heat_spike,
    "drought": _drought,
    "cold_night": _cold_night,
    "sensor_drift": _sensor_drift,
    "temp_spike_random": _temp_spike_random,
    "light_spike_burst": _light_spike_burst,
    "humidity_noise_storm": _humidity_noise_storm,
    "drift_ramp_fast": _drift_ramp_fast,
    "missing_temp_readings": _missing_temp_readings,
    "packet_loss": _packet_loss_baseline,
}


def generate_reading(scenario: str, now: datetime, ctx: ScenarioContext) -> GeneratedReading:
    """Public dispatcher — falls back to baseline on unknown scenarios."""
    fn = SCENARIOS.get(scenario or "stable", _baseline)
    return fn(now, ctx)


# ---------------------------------------------------------------------------
#  Async supervisor
# ---------------------------------------------------------------------------

class StreamSupervisor:
    """
    Single-process supervisor mapping session_id -> asyncio.Task.

    Sync FastAPI endpoints run in a worker thread, which has no asyncio loop.
    To bridge that, the FastAPI lifespan calls ``bind_loop(loop)`` once on
    startup; ``start`` / ``stop`` then use ``run_coroutine_threadsafe`` and
    ``call_soon_threadsafe`` to manipulate tasks on the main loop regardless
    of which thread invoked them.
    """

    def __init__(self) -> None:
        self._tasks: Dict[int, asyncio.Task] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # Lifespan calls this with asyncio.get_running_loop() at startup.
    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def is_streaming(self, session_id: int) -> bool:
        t = self._tasks.get(session_id)
        return bool(t and not t.done())

    def start(self, session_id: int, plant_id: int, scenario: str, interval_sec: float) -> None:
        """Idempotent — calling start twice for the same session is a no-op."""
        if self.is_streaming(session_id):
            return
        if self._loop is None or self._loop.is_closed():
            logger.warning("dummy_stream: no event loop bound; cannot start session=%s", session_id)
            return
        iv = max(0.2, float(interval_sec))
        ctx = ScenarioContext(started_at=datetime.utcnow(), stream_interval_sec=iv)
        coro = self._run(
            session_id=session_id,
            scenario=scenario or "stable",
            interval_sec=iv,
            ctx=ctx,
        )

        def _spawn():
            # Runs ON the loop thread, so create_task is safe here.
            task = self._loop.create_task(coro, name=f"dummy-stream-{session_id}")
            self._tasks[session_id] = task

        # Either we are on the loop thread already, or another (worker) thread.
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self._loop:
            _spawn()
        else:
            self._loop.call_soon_threadsafe(_spawn)

        logger.info(
            "dummy_stream: started session=%s scenario=%s interval=%.3fs",
            session_id, scenario, iv,
        )

    def stop(self, session_id: int) -> None:
        task = self._tasks.pop(session_id, None)
        if not task or task.done():
            return
        if self._loop is None or self._loop.is_closed():
            return
        # cancel() must be called on the loop thread.
        self._loop.call_soon_threadsafe(task.cancel)
        logger.info("dummy_stream: stopped session=%s", session_id)

    async def stop_all(self) -> None:
        """Called from FastAPI lifespan on shutdown."""
        for sid in list(self._tasks.keys()):
            t = self._tasks.pop(sid, None)
            if t and not t.done():
                t.cancel()
        # Allow any pending writes to flush.
        await asyncio.sleep(0)

    async def _run(self, *, session_id: int, scenario: str, interval_sec: float, ctx: ScenarioContext) -> None:
        iv = max(0.2, float(interval_sec))
        try:
            while True:
                # Use a fresh DB session per tick — request-scoped sessions
                # are not safe to hold across awaits.
                with SessionLocal() as db:
                    sess = (
                        db.query(RecordingSession)
                        .filter(RecordingSession.id == session_id)
                        .first()
                    )
                    if not sess or sess.ended_at is not None:
                        # Session was closed externally (e.g. another sample
                        # pre-empted it). Self-terminate quietly.
                        logger.info("dummy_stream: session=%s closed externally, exiting", session_id)
                        return
                    if scenario == "packet_loss" and ctx.packet_loss_skip_remaining > 0:
                        ctx.packet_loss_skip_remaining -= 1
                    else:
                        reading = generate_reading(scenario, datetime.utcnow(), ctx)
                        row, _ = store_telemetry_row(
                            db,
                            temperature=reading.temperature,
                            humidity=reading.humidity,
                            movement=reading.movement,
                            light=reading.light,
                            distance=reading.distance,
                            plant_height=reading.plant_height,
                            timestamp=reading.timestamp,
                            plant_id=sess.plant_id,
                        )
                        ctx.successful_inserts_prior += 1
                        if scenario == "packet_loss":
                            n = ctx.successful_inserts_prior
                            if (
                                n >= _PACKET_LOSS_WARMUP_STORES
                                and n % _PACKET_LOSS_BURST_EVERY_INSERTS == 0
                            ):
                                ctx.packet_loss_skip_remaining = _PACKET_LOSS_BURST_SKIP_TICKS
                await asyncio.sleep(iv)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("dummy_stream: unexpected error in session=%s", session_id)
            return


# Module-level singleton — the API layer imports this directly.
supervisor = StreamSupervisor()


# ---------------------------------------------------------------------------
#  Backfill helper (synchronous — runs in a single transaction)
# ---------------------------------------------------------------------------

def backfill_history(
    db,
    *,
    plant_id: int,
    hours: int,
    scenario: str,
    interval_sec: float = 60.0,
) -> int:
    """
    Insert back-dated telemetry for ``plant_id`` covering the past ``hours``.

    All rows are stamped directly with plant_id (NOT via session_id) so they
    appear in per-sample graphs exactly like real recording data would.
    Returns the number of rows inserted.
    """
    from models.reading import Telemetry

    step = max(0.2, float(interval_sec))
    end = datetime.utcnow()
    start = end - timedelta(hours=hours)
    ctx = ScenarioContext(started_at=start, stream_interval_sec=step)

    rows = []
    cursor = start
    while cursor <= end:
        r = generate_reading(scenario, cursor, ctx)
        rows.append(
            Telemetry(
                session_id=None,
                plant_id=plant_id,
                timestamp=r.timestamp,
                temperature=r.temperature,
                humidity=r.humidity,
                light=r.light,
                movement=r.movement,
                distance=r.distance,
                plant_height=r.plant_height,
            )
        )
        ctx.successful_inserts_prior += 1
        cursor += timedelta(seconds=step)

    if rows:
        db.bulk_save_objects(rows)
        db.commit()
    return len(rows)
