"""
Telemetry feature rows aligned with sklearn training / inference (`FEATURE_NAMES`).

One row vector per Telemetry ORM row, using rolling stats over trailing ``ROLL_WINDOW`` readings
(sorted by timestamp, per stream).
"""

from __future__ import annotations

from datetime import datetime
from statistics import fmean
from typing import Any, List, Sequence, Tuple

import numpy as np

FEATURE_VERSION = "v1"
ROLL_WINDOW = 10

FEATURE_NAMES: Tuple[str, ...] = (
    "temperature",
    "humidity",
    "light",
    "plant_height",
    "dt_sec",
    "d_temp",
    "d_hum",
    "d_light",
    "roll_mean_temp",
    "roll_std_temp",
    "roll_mean_hum",
    "roll_std_hum",
    "roll_mean_light",
    "roll_std_light",
)


def _height(r: Any) -> float | None:
    h = getattr(r, "plant_height", None)
    if h is not None:
        return float(h)
    d = getattr(r, "distance", None)
    return float(d) if d is not None else None


def _roll_stats(values: List[float | None]) -> tuple[float, float]:
    present = [float(v) for v in values if v is not None]
    if len(present) < 2:
        return float("nan"), float("nan")
    m = fmean(present)
    var = fmean((x - m) ** 2 for x in present)
    return m, var**0.5


def feature_row_at_index(rows: Sequence[Any], i: int) -> np.ndarray:
    """Return shape (len(FEATURE_NAMES),) float64 for ``rows[i]``."""
    cur = rows[i]
    prev = rows[i - 1] if i > 0 else None
    start = max(0, i - ROLL_WINDOW + 1)
    win = rows[start : i + 1]

    ts_cur = getattr(cur, "timestamp", None)
    ts_prev = getattr(prev, "timestamp", None) if prev else None
    if isinstance(ts_cur, datetime) and isinstance(ts_prev, datetime):
        dt_sec = (ts_cur - ts_prev).total_seconds()
    else:
        dt_sec = 0.0

    t0, t1 = getattr(cur, "temperature", None), getattr(prev, "temperature", None) if prev else None
    h0, h1 = getattr(cur, "humidity", None), getattr(prev, "humidity", None) if prev else None
    l0, l1 = getattr(cur, "light", None), getattr(prev, "light", None) if prev else None

    d_temp = (float(t0) - float(t1)) if t0 is not None and t1 is not None else 0.0
    d_hum = (float(h0) - float(h1)) if h0 is not None and h1 is not None else 0.0
    d_light = (float(l0) - float(l1)) if l0 is not None and l1 is not None else 0.0

    temps = [getattr(r, "temperature", None) for r in win]
    hums = [getattr(r, "humidity", None) for r in win]
    lights = [getattr(r, "light", None) for r in win]
    rmt, rst = _roll_stats(temps)
    rmh, rsh = _roll_stats(hums)
    rml, rsl = _roll_stats(lights)

    vec = np.array(
        [
            float(t0) if t0 is not None else np.nan,
            float(h0) if h0 is not None else np.nan,
            float(l0) if l0 is not None else np.nan,
            float(_height(cur)) if _height(cur) is not None else np.nan,
            float(dt_sec),
            d_temp,
            d_hum,
            d_light,
            rmt,
            rst,
            rmh,
            rsh,
            rml,
            rsl,
        ],
        dtype=np.float64,
    )
    return vec


def telemetry_rows_to_matrix(rows: Sequence[Any]) -> np.ndarray:
    """Shape (n_rows, n_features)."""
    if not rows:
        return np.zeros((0, len(FEATURE_NAMES)), dtype=np.float64)
    return np.vstack([feature_row_at_index(rows, i) for i in range(len(rows))])


def iter_plant_feature_rows(rows: Iterable[Any]) -> Tuple[np.ndarray, List[Any]]:
    """``rows`` must be sorted by timestamp ascending, single plant."""
    seq = list(rows)
    if not seq:
        return np.zeros((0, len(FEATURE_NAMES)), dtype=np.float64), []
    X = telemetry_rows_to_matrix(seq)
    return X, seq
