"""
FR1 / FR2 - Telemetry ingest, store, query.

Service layer keeps SQL behind a small surface so the API and dummy_stream
service can share the same code path. Two query-side concerns deserve a note:

* ``plant_ids`` (multi-select) filtering - the chart can compare several
  samples in one chart, but the backend still groups everything into one
  series payload to keep the wire shape unchanged for legacy callers.
  Per-sample series for compare-mode is built on top via
  ``get_per_plant_timeseries_data``.

* Binning / downsampling. Live charts at 1-second resolution over 72 h
  would push hundreds of thousands of points to the browser. ``bin_seconds``
  buckets readings into fixed time windows and returns the mean per window
  using simple Python aggregation (no DB-specific date_trunc needed so the
  same logic works on SQLite + Postgres).
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

from sqlalchemy.orm import Session

from models.device import Device
from models.reading import Telemetry
from services.recording_session_service import get_any_open_session, get_open_session_for_plant


def store_telemetry_row(
    db: Session,
    *,
    temperature: Optional[float] = None,
    humidity: Optional[float] = None,
    movement: Optional[bool] = None,
    light: Optional[float] = None,
    distance: Optional[float] = None,
    plant_height: Optional[float] = None,
    timestamp: Optional[datetime] = None,
    device_id: Optional[int] = None,
    bt_name: Optional[str] = None,
    plant_id: Optional[int] = None,
) -> Telemetry:
    """Attach to an open recording session for the given plant when possible.

    If a ``plant_id`` is provided, prefer the open session for that plant so multiple users
    can record different samples concurrently. If none, fall back to the most recently started
    open session (legacy Pi without ``plant_id``).

    If there is *no* open session, an optional ``plant_id`` from ingest still tags the row for
    threshold evaluation against that sample's control profile (backfill / bench mode).
    """
    now = datetime.fromtimestamp(key, tz=timezone.utc)
    open_sess = None
    if plant_id is not None:
        open_sess = get_open_session_for_plant(db, plant_id)
    else:
        open_sess = None  # do NOT guess
    sid = open_sess.id if open_sess else None
    pid = open_sess.plant_id if open_sess else None
    if pid is None and plant_id is not None:
        pid = plant_id

    if device_id is not None:
        dev = db.query(Device).filter(Device.id == device_id).first()
        if dev:
            dev.last_seen_at = now
    elif bt_name:
        dev = db.query(Device).filter(Device.bt_name == bt_name).first()
        if dev:
            dev.last_seen_at = now

    row = Telemetry(
        session_id=sid,
        plant_id=pid,
        timestamp=timestamp or now,
        temperature=temperature,
        humidity=humidity,
        light=float(light) if light is not None else None,
        movement=movement,
        distance=distance,
        plant_height=plant_height,
    )
    db.add(row)
    if pid is not None:
        from services.threshold_service import evaluate_telemetry_row

        evaluate_telemetry_row(db, plant_id=pid, session_id=sid, row=row)
    db.commit()
    db.refresh(row)
    try:
        from services.anomaly_runtime import run_detection_and_persist

        run_detection_and_persist(db, row)
    except Exception:
        logger.exception("anomaly detection failed for telemetry id=%s", getattr(row, "id", None))
    return row


def get_latest_reading(db: Session) -> Optional[Dict[str, Any]]:
    row = db.query(Telemetry).order_by(Telemetry.timestamp.desc()).first()
    if not row:
        return None
    return {
        "temperature": row.temperature,
        "humidity": row.humidity,
        "light": row.light,
        "height": row.plant_height,
        "motion": row.movement,
        "distance": row.distance,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "session_id": row.session_id,
    }


def get_latest_reading_for_plant_ids(db: Session, plant_ids: List[int]) -> Optional[Dict[str, Any]]:
    if not plant_ids:
        return None
    row = (
        db.query(Telemetry)
        .filter(Telemetry.plant_id.in_(plant_ids))
        .order_by(Telemetry.timestamp.desc())
        .first()
    )
    if not row:
        return None
    return {
        "temperature": row.temperature,
        "humidity": row.humidity,
        "light": row.light,
        "height": row.plant_height,
        "motion": row.movement,
        "distance": row.distance,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "session_id": row.session_id,
    }


def _build_payload(rows: Iterable[Telemetry], bin_seconds: Optional[int]) -> Dict[str, Any]:
    """
    Convert a sorted iterable of Telemetry rows into the {timestamps, ...} payload.
    When ``bin_seconds`` > 0, mean-bucket numeric series so very long ranges stay
    chartable. Aggregation done in Python so behaviour matches across SQLite +
    Postgres without dialect-specific SQL.
    """
    rows = list(rows)
    if not bin_seconds or bin_seconds < 1:
        ts, temp, hum, light, height = [], [], [], [], []
        for r in rows:
            ts.append(r.timestamp.isoformat() if r.timestamp else "")
            temp.append(r.temperature)
            hum.append(r.humidity)
            light.append(r.light)
            height.append(r.plant_height)
        return {
            "timestamps": ts, "temperature": temp, "humidity": hum,
            "light": light, "plant_height": height,
            "bin_seconds": 0, "row_count": len(rows),
        }

    # Bucket key = floor((unix_ts) / bin_seconds) * bin_seconds.
    buckets: Dict[int, List[Telemetry]] = defaultdict(list)
    for r in rows:
        if not r.timestamp:
            continue
        key = int(r.timestamp.timestamp() // bin_seconds) * bin_seconds
        buckets[key].append(r)

    ts, temp, hum, light, height = [], [], [], [], []
    for key in sorted(buckets.keys()):
        bucket = buckets[key]
        ts.append(datetime.utcfromtimestamp(key).isoformat())
        # mean over present (non-None) numeric values; None if the bucket has
        # no numeric values for that channel (so the chart can show a gap).
        for src_attr, dest in (
            ("temperature", temp), ("humidity", hum),
            ("light", light), ("plant_height", height),
        ):
            vals = [getattr(r, src_attr) for r in bucket if getattr(r, src_attr) is not None]
            dest.append(round(mean(vals), 3) if vals else None)

    return {
        "timestamps": ts, "temperature": temp, "humidity": hum,
        "light": light, "plant_height": height,
        "bin_seconds": bin_seconds, "row_count": len(rows),
    }


def get_telemetry_timeseries_data(
    db: Session,
    hours: int = 24,
    plant_id: Optional[int] = None,
    plant_ids: Optional[List[int]] = None,
    bin_seconds: Optional[int] = None,
    session_id: Optional[int] = None,
):
    """
    Single combined series in the legacy {timestamps, temperature, ...} shape.

    * ``plant_id`` (legacy) -> single sample filter. Kept so existing callers
      (frontend api.js, /api/plants/{id}/timeseries) don't break.
    * ``plant_ids`` -> union of multiple samples in one series (used by the
      compare-mode "all of these stacked into one series" mode).
    * ``bin_seconds`` -> optional mean downsampling for long ranges.
    * ``session_id`` -> restrict to one recording session (excludes backfill
      rows with ``session_id`` NULL and other sessions on the same plant).
    """
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    q = db.query(Telemetry).filter(Telemetry.timestamp >= cutoff_time)

    if session_id is not None:
        q = q.filter(Telemetry.session_id == session_id)

    if plant_ids:
        q = q.filter(Telemetry.plant_id.in_(plant_ids))
    elif plant_id is not None:
        q = q.filter(Telemetry.plant_id == plant_id)

    rows = q.order_by(Telemetry.timestamp).all()
    return _build_payload(rows, bin_seconds)


def get_per_plant_timeseries_data(
    db: Session,
    plant_ids: List[int],
    hours: int = 24,
    bin_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Compare-mode payload: returns {plants: [{plant_id, timestamps, temperature, ...}, ...]}
    so the chart can render one coloured line per sample without re-querying.
    Includes a ``timestamps`` field per series rather than a shared X axis,
    because samples almost never have aligned tick times.
    """
    if not plant_ids:
        return {"plants": [], "bin_seconds": bin_seconds or 0}
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    rows = (
        db.query(Telemetry)
        .filter(Telemetry.timestamp >= cutoff_time, Telemetry.plant_id.in_(plant_ids))
        .order_by(Telemetry.plant_id, Telemetry.timestamp)
        .all()
    )
    by_plant: Dict[int, List[Telemetry]] = defaultdict(list)
    for r in rows:
        by_plant[r.plant_id].append(r)
    series = []
    for pid in plant_ids:
        series.append({"plant_id": pid, **_build_payload(by_plant.get(pid, []), bin_seconds)})
    return {"plants": series, "bin_seconds": bin_seconds or 0}
