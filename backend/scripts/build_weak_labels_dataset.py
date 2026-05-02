#!/usr/bin/env python3
"""
Build a weak-label dataset from Telemetry + anomaly_detection_events.

Positive rows: anomalies linked by telemetry_id or within ±NORMAL_BUFFER_SEC of an event anchor
(already-linked telemetry timestamps else event.created_at). Multiple types merged by priority rule.

Negative (normal): rows assigned label ``normal``.

Outputs Parquet (+ optional CSV) with raw telemetry columns and ``weak_label``.
Run from repo root or backend: ``python scripts/build_weak_labels_dataset.py``

Requires: sqlalchemy, pandas, pyarrow or fastparquet (for parquet).
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.normpath(os.path.join(_SCRIPT_DIR, ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from sqlalchemy.orm import Session  # noqa: E402

from database import SessionLocal  # noqa: E402
from models.anomaly_detection_event import AnomalyDetectionEvent  # noqa: E402
from models.reading import Telemetry  # noqa: E402


# Highest priority wins (deterministic multiclass supervision when several rules fire nearby).
PRIORITY_RANK = (
    "spike",
    "level_shift",
    "ewma_breach",
    "dropout",
    "missing_data",
    "drift",
    "noise",
    "correlation",
    "seasonal",
)


def _rank(t: str) -> int:
    t = str(t).strip().lower()
    try:
        return PRIORITY_RANK.index(t)
    except ValueError:
        return len(PRIORITY_RANK) + 1


def merge_types(types: list[str]) -> str:
    if not types:
        return "normal"
    clean = sorted({str(x).strip().lower() for x in types})
    return min(clean, key=lambda t: (_rank(t), t))


def _height(r: Telemetry) -> float | None:
    if r.plant_height is not None:
        return float(r.plant_height)
    if r.distance is not None:
        return float(r.distance)
    return None


NORMAL_BUFFER_SEC = 120


def anchor_time(sess: Session, evt: AnomalyDetectionEvent, cache: dict[int, datetime]) -> datetime:
    tid = evt.telemetry_id
    if tid is None:
        return evt.created_at
    if tid not in cache:
        row = sess.query(Telemetry).filter(Telemetry.id == tid).first()
        cache[tid] = row.timestamp if row and row.timestamp else evt.created_at
    return cache[tid]


def load_frames(sess: Session, hours: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    trows = (
        sess.query(Telemetry)
        .filter(Telemetry.plant_id.isnot(None), Telemetry.timestamp >= cutoff)
        .order_by(Telemetry.plant_id, Telemetry.timestamp, Telemetry.id)
        .all()
    )

    telemetry_df = pd.DataFrame(
        [
            {
                "telemetry_id": r.id,
                "plant_id": r.plant_id,
                "session_id": r.session_id,
                "timestamp": r.timestamp,
                "temperature": r.temperature,
                "humidity": r.humidity,
                "light": r.light,
                "movement": r.movement,
                "distance": r.distance,
                "plant_height": r.plant_height,
            }
            for r in trows
        ]
    )

    erows = (
        sess.query(AnomalyDetectionEvent)
        .filter(AnomalyDetectionEvent.created_at >= cutoff - timedelta(seconds=NORMAL_BUFFER_SEC))
        .all()
    )

    anchors: dict[int, datetime] = {}
    events_records: list[dict[str, Any]] = []
    for e in erows:
        events_records.append(
            {
                "plant_id": e.plant_id,
                "telemetry_id": e.telemetry_id,
                "anomaly_type": str(e.anomaly_type).strip().lower(),
                "anchor": anchor_time(sess, e, anchors),
                "created_at": e.created_at,
            }
        )
    events_df = pd.DataFrame(events_records)

    # Normalise anomaly_type strings sometimes stored oddly
    if not events_df.empty:
        events_df["anomaly_type"] = events_df["anomaly_type"].str.strip().str.lower()

    return telemetry_df, events_df


def label_telemetry(
    telemetry_df: pd.DataFrame,
    events_df: pd.DataFrame,
) -> pd.Series:
    if telemetry_df.empty:
        return pd.Series(dtype=object)

    labels = []
    for _, row in telemetry_df.iterrows():
        pid = int(row.plant_id)
        ts = row.timestamp
        if ts is None or (isinstance(ts, float) and math.isnan(ts)):
            labels.append("normal")
            continue
        t0 = ts if hasattr(ts, "timestamp") else pd.Timestamp(ts).to_pydatetime()
        cand: list[str] = []

        if not events_df.empty:
            subset = events_df[events_df["plant_id"] == pid]
            for _, ev in subset.iterrows():
                if pd.notna(ev.telemetry_id) and int(ev.telemetry_id) == int(row.telemetry_id):
                    cand.append(str(ev.anomaly_type))
                    continue
                ea = ev["anchor"]
                if ea is None or pd.isna(ea):
                    continue
                t_e = ea if hasattr(ea, "timestamp") else pd.Timestamp(ea).to_pydatetime()
                if abs((t0 - t_e).total_seconds()) <= NORMAL_BUFFER_SEC:
                    cand.append(str(ev.anomaly_type))

        labels.append(merge_types(cand) if cand else "normal")

    return pd.Series(labels, index=telemetry_df.index)


def main() -> None:
    ap = argparse.ArgumentParser(description="Export weak-label telemetry parquet for sklearn.")
    ap.add_argument("--hours", type=int, default=8760, help="Look-back window for telemetry/events")
    ap.add_argument(
        "--out",
        default=os.path.join(_BACKEND_ROOT, "artifacts", "weak_labels_dataset.parquet"),
        help="Output path (.parquet or .csv)",
    )
    args = ap.parse_args()

    db: Session = SessionLocal()
    try:
        tdf, edf = load_frames(db, args.hours)
        tdf = tdf.copy()
        tdf["weak_label"] = label_telemetry(tdf, edf)
        out_path = os.path.abspath(args.out)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        if out_path.endswith(".csv"):
            tdf.to_csv(out_path, index=False)
        else:
            tdf.to_parquet(out_path, index=False)
        print(f"Wrote {len(tdf)} rows to {out_path}")
        print(tdf["weak_label"].value_counts().head(15).to_string())
    finally:
        db.close()


if __name__ == "__main__":
    main()
